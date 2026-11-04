// Copyright 2026 Abu M53 contributors. SPDX-License-Identifier: Apache-2.0
using UnrealBuildTool;
public class AbuM53Render : ModuleRules
{
    public AbuM53Render(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        CppStandard = CppStandardVersion.Cpp20;
        bEnableExceptions = true;
        PrivateDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "Projects", "RenderCore", "RHI", "Renderer", "AbuM53Runtime" });
    }
}
