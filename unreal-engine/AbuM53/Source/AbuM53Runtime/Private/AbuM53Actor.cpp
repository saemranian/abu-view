// SPDX-License-Identifier: Apache-2.0
#include "AbuM53Actor.h"
#include "AbuM53Component.h"
AAbuM53Actor::AAbuM53Actor()
{
    SplatComponent = CreateDefaultSubobject<UAbuM53Component>(TEXT("AbuM53"));
    SetRootComponent(SplatComponent);
}
