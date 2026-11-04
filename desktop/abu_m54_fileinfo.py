"""Human-readable details for any file or folder opened in Abu M54."""
import csv
import datetime
from pathlib import Path
import numpy as np


def human_size(value):
    value=float(value)
    for unit in ['B','KB','MB','GB','TB']:
        if value<1024 or unit=='TB':return f'{value:.0f} {unit}' if unit=='B' else f'{value:.2f} {unit}'
        value/=1024


def read_ply_header(path):
    """Return PLY format, element table and comments from the text header only."""
    info=dict(format='?',elements=[],comments=[])
    with open(path,'rb') as stream:
        first=stream.readline().strip()
        if first!=b'ply':return None
        for _ in range(500):
            line=stream.readline().decode('ascii','replace').strip()
            if not line or line=='end_header':break
            parts=line.split()
            if parts[0]=='format':info['format']=' '.join(parts[1:])
            elif parts[0]=='comment':info['comments'].append(line[8:])
            elif parts[0]=='element' and len(parts)>=3:info['elements'].append(dict(name=parts[1],count=int(parts[2]),properties=[]))
            elif parts[0]=='property' and info['elements']:info['elements'][-1]['properties'].append(parts[-1])
    return info


def kind_of(path,scene):
    name=path.name.lower();suffix=path.suffix.lower()
    if path.is_dir():return 'Result folder','folder'
    if suffix=='.ply':return ('Gaussian splats (3DGS)' if scene.get('gaussians') is not None else 'PLY point cloud'),'cloud'
    if suffix=='.csv':return ('Camera alignment CSV' if scene.get('centers') else 'CSV table'),'cameras'
    if name in {'images.bin','images.txt'}:return 'COLMAP camera poses','cameras'
    if name in {'points3d.bin','points3d.txt'}:return 'COLMAP sparse points','cloud'
    if name.startswith('poses_'):return 'ACE0 camera poses','cameras'
    if suffix=='.json':return 'Reconstruction JSON','scene'
    if suffix=='.npz':return 'M54 scene archive','scene'
    if suffix in {'.xyz','.pts'}:return 'Point list','cloud'
    if suffix=='.txt':return 'Camera trajectory text','cameras'
    return 'Scene file','scene'


def fmt(values,digits=6):return ', '.join(f'{float(v):.{digits}g}' for v in values)


def describe_source(scene):
    """Build [(section, [(label,value),...]), ...] plus a short type label and glyph key."""
    source=Path(str(scene.get('source','')));sections=[];kind,glyph=kind_of(source,scene) if str(source) not in {'','.'} else ('Scene','scene')
    rows=[('Name',source.name or str(source)),('Type',kind),('Location',str(source.parent))]
    try:
        if source.is_file():stat=source.stat();rows+=[('Size',human_size(stat.st_size)),('Modified',datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'))]
        elif source.is_dir():rows.append(('Contents',f'{sum(1 for _ in source.iterdir()):,} items'))
    except OSError:pass
    sections.append(('File',rows))
    points=scene.get('points',np.empty((0,3)));cameras=scene.get('centers',{});controls=scene.get('controls',{})
    shown=len(points);total=int(scene.get('total_points',shown))
    if scene.get('gaussians') is not None:
        summary=[('Gaussian splats',f"{scene['gaussians'].count:,} · full GPU asset"),('Picking / fallback preview',f'{shown:,} points')]
    else:
        summary=[('Cloud points',f'{shown:,}'+(f' shown of {total:,}' if total>shown else ''))]
    summary += [('Cameras',f'{len(cameras):,}'),('Controls',f'{len(controls):,}')]
    if shown:
        low,high=points.min(0),points.max(0);summary+=[('Cloud min',fmt(low)),('Cloud max',fmt(high)),('Cloud size',fmt(high-low))]
    if cameras:
        xyz=np.array(list(cameras.values()));summary+=[('Camera min',fmt(xyz.min(0))),('Camera max',fmt(xyz.max(0)))]
        if len(xyz)>1:
            steps=np.linalg.norm(np.diff(xyz,axis=0),axis=1);summary+=[('Path length',f'{steps.sum():.6g}'),('Mean step',f'{steps.mean():.6g}')]
    if scene.get('extent'):summary.append(('Scene extent',f"{float(scene['extent']):.6g}"))
    sections.append(('Scene',summary))
    companions=[(t,Path(scene[k]).name) for t,k in [('Cameras from','companion_cameras'),('Cloud from','companion_cloud')] if scene.get(k)]
    if companions:sections.append(('Companion files',companions))
    if source.suffix.lower()=='.ply' and source.is_file():
        try:header=read_ply_header(source)
        except (OSError,ValueError):header=None
        if header:
            vertex=next((e for e in header['elements'] if e['name']=='vertex'),None);props=vertex['properties'] if vertex else []
            splat=all(p in props for p in ['opacity','scale_0','rot_0']) and any(p.startswith('f_dc') for p in props)
            rows=[('Format',header['format']),('Vertices',f"{vertex['count']:,}" if vertex else '—'),('Kind','3D Gaussian Splat' if splat else 'Point cloud'),
                  ('Colors','yes' if {'red','green','blue'}<=set(props) or 'f_dc_0' in props else 'no'),('Normals','yes' if 'nx' in props else 'no')]
            if vertex:rows.append(('Properties',f"{len(props)}: "+', '.join(props[:14])+(' …' if len(props)>14 else '')))
            others=[f"{e['name']} ×{e['count']:,}" for e in header['elements'] if e['name']!='vertex']
            if others:rows.append(('Other elements',', '.join(others)))
            if header['comments']:rows.append(('Comments',' | '.join(header['comments'][:3])))
            sections.append(('PLY header',rows))
    if source.suffix.lower()=='.csv' and source.is_file():
        try:
            with source.open(encoding='utf-8-sig',newline='') as stream:
                reader=csv.reader(stream);columns=next(reader,[]);count=sum(1 for _ in reader)
            sections.append(('CSV table',[('Rows',f'{count:,}'),('Columns',f'{len(columns)}: '+', '.join(columns[:10])+(' …' if len(columns)>10 else ''))]))
        except (OSError,UnicodeDecodeError,csv.Error):pass
    return kind,glyph,sections
