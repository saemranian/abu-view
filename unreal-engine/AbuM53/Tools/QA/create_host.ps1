param(
    [Parameter(Mandatory = $true)][string]$ProjectDirectory,
    [string]$PluginDirectory,
    [string]$EngineAssociation = '5.8',
    [string]$EngineDirectory
)
$ErrorActionPreference = 'Stop'
if (-not $PluginDirectory) {
    $PluginDirectory = [IO.Path]::Combine($PSScriptRoot, '../..')
}
if (-not $EngineDirectory) {
    $EngineDirectory = "C:/Program Files/Epic Games/UE_$EngineAssociation"
}
$m53Plugin = [IO.Path]::GetFullPath($PluginDirectory)
$m53Host = [IO.Path]::GetFullPath($ProjectDirectory)
if (-not (Test-Path -LiteralPath $m53Plugin -PathType Container)) {
    throw "Plugin directory does not exist: $m53Plugin"
}
New-Item -ItemType Directory -Path $m53Host -Force | Out-Null
$m53ProjectPath = Join-Path $m53Host 'AbuM53Host.uproject'
if (-not (Test-Path -LiteralPath $m53ProjectPath)) {
    $m53EnabledPlugins = @(
        @{Name='AbuM53'; Enabled=$true},
        @{Name='PythonScriptPlugin'; Enabled=$true},
        @{Name='EditorScriptingUtilities'; Enabled=$true}
    )
    $m53Marketplace = [IO.Path]::Combine($EngineDirectory, 'Engine/Plugins/Marketplace')
    if (Test-Path -LiteralPath $m53Marketplace -PathType Container) {
        Get-ChildItem -LiteralPath $m53Marketplace -Filter '*.uplugin' -Recurse |
            Sort-Object BaseName -Unique | ForEach-Object {
                if ($_.BaseName -notin @('AbuM53','PythonScriptPlugin','EditorScriptingUtilities')) {
                    $m53EnabledPlugins += @{Name=$_.BaseName; Enabled=$false}
                }
            }
    }
    $m53Project = [ordered]@{
        FileVersion = 3
        EngineAssociation = $EngineAssociation
        Category = 'Tests'
        Description = 'Abu M53 isolated validation host'
        DisableEnginePluginsByDefault = $false
        AdditionalPluginDirectories = @([IO.Path]::GetDirectoryName($m53Plugin))
        Plugins = $m53EnabledPlugins
    }
    $m53Project | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $m53ProjectPath -Encoding utf8
}
$m53Config = Join-Path $m53Host 'Config'
New-Item -ItemType Directory -Path $m53Config -Force | Out-Null
$m53EngineIni = Join-Path $m53Config 'DefaultEngine.ini'
if (-not (Test-Path -LiteralPath $m53EngineIni)) {
    @'
[/Script/Engine.RendererSettings]
r.DefaultFeature.AutoExposure=False
r.DefaultFeature.MotionBlur=False
r.AntiAliasingMethod=0
r.DynamicGlobalIlluminationMethod=0
r.ReflectionMethod=0

[/Script/WindowsTargetPlatform.WindowsTargetSettings]
DefaultGraphicsRHI=DefaultGraphicsRHI_DX12
'@ | Set-Content -LiteralPath $m53EngineIni -Encoding utf8
}
Write-Output $m53ProjectPath
