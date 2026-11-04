// SPDX-License-Identifier: Apache-2.0
using UnrealBuildTool;
using System.IO;
public class AbuM53Runtime : ModuleRules
{
    public AbuM53Runtime(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        CppStandard = CppStandardVersion.Cpp20;
        bEnableExceptions = true;
        bUseUnity = false;
        PublicDefinitions.Add("ABUM53_CORE_API=ABUM53RUNTIME_API");
        PublicDependencyModuleNames.AddRange(new [] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.AddRange(new [] { "Json", "JsonUtilities", "Projects" });
        AddEngineThirdPartyPrivateStaticDependencies(Target, "zlib");
        PublicIncludePaths.Add(Path.GetFullPath(Path.Combine(ModuleDirectory, "../../Core/Include")));
        PrivateIncludePaths.Add(Path.GetFullPath(Path.Combine(ModuleDirectory, "../../ThirdParty/Zstd")));
    }
}
