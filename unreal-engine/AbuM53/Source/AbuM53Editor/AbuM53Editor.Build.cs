// SPDX-License-Identifier: Apache-2.0
using UnrealBuildTool;
public class AbuM53Editor : ModuleRules
{
    public AbuM53Editor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new [] { "Core", "CoreUObject", "Engine", "UnrealEd", "AbuM53Runtime" });
        PrivateDependencyModuleNames.AddRange(new [] { "AssetTools", "AssetRegistry", "Slate", "SlateCore", "ToolMenus", "Projects" });
    }
}
