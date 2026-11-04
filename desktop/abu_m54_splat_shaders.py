# SPDX-License-Identifier: Apache-2.0
"""Original M54 GLSL programs: project anisotropic Gaussians, GPU sort, composite.

No upstream renderer source is embedded. Real SH use normalized associated
Legendre polynomials (Condon-Shortley phase), l*l+l+m coefficient ordering.
See licenses/M54-GAUSSIAN-NOTICE.txt for the precise license boundary.
"""

PREPARE = r'''#version 430
layout(local_size_x=256) in;
layout(std430,binding=0) readonly buffer Assets { float asset[]; };
layout(std430,binding=1) buffer Order { uvec2 order[]; };
struct Projected { vec4 rect; vec4 conic; vec4 colorDepth; };
layout(std430,binding=2) writeonly buffer Output { Projected projected[]; };
uniform uint count;
uniform uint padded;
uniform mat4 modelView;
uniform mat4 projection;
uniform vec2 viewport;
uniform vec3 cameraObject;

float shBasis(int l,int m,vec3 d) {
    int a=abs(m);
    float p=1.;
    float t=sqrt(max(0.,1.-d.z*d.z));
    for(int i=1;i<=a;++i) p*=-(2.*float(i)-1.)*t;
    if(l>a) {
        float prev=p; p=d.z*(2.*float(a)+1.)*prev;
        for(int n=a+2;n<=l;++n) {
            float next=((2.*float(n)-1.)*d.z*p-float(n+a-1)*prev)/float(n-a);
            prev=p; p=next;
        }
    }
    float ratio=1.;
    for(int i=l-a+1;i<=l+a;++i) ratio/=float(i);
    float basis=sqrt((2.*float(l)+1.)/(4.*3.141592653589793)*ratio)*p;
    if(m!=0) basis*=sqrt(2.)*(m>0?cos(float(a)*atan(d.y,d.x)):sin(float(a)*atan(d.y,d.x)));
    return basis;
}
void main() {
    uint i=gl_GlobalInvocationID.x;
    if(i>=padded) return;
    order[i]=uvec2(0u,0xffffffffu);
    if(i>=count) return;
    uint b=i*64u;
    vec3 pos=vec3(asset[b],asset[b+1u],asset[b+2u]);
    vec4 eye=modelView*vec4(pos,1.);
    vec4 clip=projection*eye;
    if(clip.w<=0. || clip.z < -clip.w || clip.z>clip.w) return;
    vec3 s=vec3(asset[b+4u],asset[b+5u],asset[b+6u]);
    float w=asset[b+8u],x=asset[b+9u],y=asset[b+10u],z=asset[b+11u];
    mat3 rotation=mat3(
        1.-2.*(y*y+z*z),2.*(x*y+w*z),2.*(x*z-w*y),
        2.*(x*y-w*z),1.-2.*(x*x+z*z),2.*(y*z+w*x),
        2.*(x*z+w*y),2.*(y*z-w*x),1.-2.*(x*x+y*y));
    mat3 a=mat3(modelView)*rotation*mat3(s.x,0,0,0,s.y,0,0,0,s.z);
    // Perspective Jacobian in pixel coordinates (OpenGL eye forward is -Z).
    float depth=-eye.z;
    float fx=.5*viewport.x*projection[0][0],fy=.5*viewport.y*projection[1][1];
    // Bound the first-order approximation outside a 30% frustum guard band.
    // The true projected center is retained. Otherwise an offscreen mean near
    // the eye plane produces a huge false ellipse covering the whole image.
    vec2 slope=clamp(eye.xy/depth,-1.3/vec2(projection[0][0],projection[1][1]),
                                1.3/vec2(projection[0][0],projection[1][1]));
    vec3 jx=vec3(fx/depth,0.,fx*slope.x/depth);
    vec3 jy=vec3(0.,fy/depth,fy*slope.y/depth);
    vec3 u=transpose(a)*jx,v=transpose(a)*jy;
    // Lagrange's identity avoids subtracting two nearly equal large products
    // for thin splats. Normalize first to keep products in float32 range.
    vec3 largest=max(abs(u),abs(v));
    float magnitude=max(1.,max(largest.x,max(largest.y,largest.z)));
    if(isnan(magnitude) || isinf(magnitude)) return;
    float invMagnitude=1./magnitude;
    u*=invMagnitude;v*=invMagnitude;
    float lowPass=.3*invMagnitude*invMagnitude;
    float uu=dot(u,u),vv=dot(v,v);
    float cxx=uu+lowPass,cxy=dot(u,v),cyy=vv+lowPass;
    vec3 area=cross(u,v);
    float det=dot(area,area)+lowPass*(uu+vv)+lowPass*lowPass;
    if(det<=0. || isnan(det) || isinf(det)) return;
    vec2 center=(clip.xy/clip.w*.5+.5)*viewport;
    vec2 radius=3.*magnitude*sqrt(vec2(cxx,cyy));
    if(any(isnan(radius)) || any(isinf(radius))) return;
    if(any(lessThan(center+radius,vec2(0.))) || any(greaterThan(center-radius,viewport))) return;
    vec3 direction=normalize(pos-cameraObject);
    vec3 color=vec3(.5);
    int degree=int(asset[b+7u]);
    for(int l=0;l<=degree;++l) for(int m=-l;m<=l;++m) {
        uint k=uint(l*l+l+m);
        color+=shBasis(l,m,direction)*vec3(asset[b+12u+k],asset[b+28u+k],asset[b+44u+k]);
    }
    projected[i].rect=vec4(center,radius);
    // Inverse Cholesky factors, evaluated as a sum of squares in the fragment
    // shader. The former expanded quadratic could become negative and turn
    // distant tails opaque after exp(-q/2), despite a valid input covariance.
    float rootX=sqrt(cxx),rootDet=sqrt(det);
    projected[i].conic=vec4(invMagnitude/rootX,
        -cxy*invMagnitude/(rootX*rootDet),rootX*invMagnitude/rootDet,asset[b+3u]);
    projected[i].colorDepth=vec4(max(color,vec3(0.)),clip.z/clip.w);
    order[i]=uvec2(floatBitsToUint(depth),i);
}
'''

# Hybrid bitonic: merge within shared memory for strides <256. Deterministic
# depth-descending order with ascending source index as a tie breaker.
SORT = r'''#version 430
layout(local_size_x=256) in;
layout(std430,binding=1) buffer Order { uvec2 order[]; };
uniform uint padded;
uniform uint stage;
uniform uint stride;
uniform uint localPass;
shared uvec2 tile[256];
bool lessKey(uvec2 a,uvec2 b) {return a.x<b.x || (a.x==b.x && a.y>b.y);}
void main() {
    uint i=gl_GlobalInvocationID.x,t=gl_LocalInvocationID.x;
    if(localPass==0u) {
        if(i>=padded) return;
        uint other=i^stride;
        if(other<=i || other>=padded) return;
        uvec2 a=order[i],b=order[other];
        bool descending=(i&stage)==0u;
        if(lessKey(a,b)==descending) {order[i]=b;order[other]=a;}
        return;
    }
    tile[t]=i<padded?order[i]:uvec2(0u,0xffffffffu);
    barrier();
    uint first=localPass==1u?2u:stage;
    uint last=localPass==1u?256u:stage;
    for(uint k=first;k<=last;k*=2u) {
        uint start=localPass==1u?k/2u:128u;
        for(uint j=start;j>0u;j/=2u) {
            uvec2 a=tile[t],b=tile[t^j];
            bool descending=(i&k)==0u;
            bool low=(t&j)==0u;
            bool swap=low?(lessKey(a,b)==descending):(lessKey(b,a)==descending);
            barrier();
            tile[t]=swap?b:a;
            barrier();
        }
    }
    if(i<padded) order[i]=tile[t];
}
'''

VERTEX = r'''#version 430
layout(std430,binding=1) readonly buffer Order { uvec2 order[]; };
struct Projected {vec4 rect;vec4 conic;vec4 colorDepth;};
layout(std430,binding=2) readonly buffer Output {Projected projected[];};
uniform vec2 viewport;
out vec2 delta;
flat out vec4 conic;
flat out vec3 color;
void main() {
    uint index=order[gl_InstanceID].y;
    if(index==0xffffffffu) {gl_Position=vec4(2.,2.,2.,1.);delta=vec2(0);conic=vec4(0);color=vec3(0);return;}
    vec2 corners[6]=vec2[6](vec2(-1,-1),vec2(1,-1),vec2(1,1),vec2(-1,-1),vec2(1,1),vec2(-1,1));
    Projected p=projected[index];
    // Clip only the bounding rectangle, not the Gaussian footprint. This
    // avoids huge offscreen vertices while preserving exact pixel offsets.
    vec2 pixel=clamp(p.rect.xy+corners[gl_VertexID]*p.rect.zw,vec2(-1.),viewport+1.);
    delta=pixel-p.rect.xy;
    gl_Position=vec4(pixel/viewport*2.-1.,p.colorDepth.w,1.);
    conic=p.conic;color=p.colorDepth.xyz;
}
'''

FRAGMENT = r'''#version 430
in vec2 delta;
flat in vec4 conic;
flat in vec3 color;
out vec4 result;
void main() {
    vec2 whitened=vec2(conic.x*delta.x,conic.y*delta.x+conic.z*delta.y);
    float q=dot(whitened,whitened);
    if(q>9. || isnan(q) || isinf(q)) discard;
    float alpha=min(.99,conic.w*exp(-.5*q));
    if(alpha<1./255.) discard;
    result=vec4(color*alpha,alpha);
}
'''
