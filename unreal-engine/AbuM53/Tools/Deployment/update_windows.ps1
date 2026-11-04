param(
    [string]$EngineDirectory = 'C:/Program Files/Epic Games/UE_5.8',
    [Parameter(Mandatory = $true)][string]$WorkDirectory,
    [string]$Python = 'python',
    [switch]$BuildOnly,
    [switch]$ReplaceUnreleased
)
$ErrorActionPreference = 'Stop'
$m53Helper = Join-Path $PSScriptRoot 'windows.py'
$m53Work = [IO.Path]::GetFullPath($WorkDirectory)
& $Python $m53Helper stage --directory $m53Work
if ($LASTEXITCODE -ne 0) { throw 'Snapshot failed' }
$m53Uat = Join-Path $EngineDirectory 'Engine/Build/BatchFiles/RunUAT.bat'
$m53Descriptor = Join-Path $m53Work 'Source/AbuM53/AbuM53.uplugin'
$m53Package = Join-Path $m53Work 'Package'
$m53PreviousLog = $env:uebp_LogFolder
try {
    $env:uebp_LogFolder = Join-Path $m53Work 'Logs'
    & $m53Uat BuildPlugin "-Plugin=$m53Descriptor" "-Package=$m53Package" '-TargetPlatforms=Win64' '-HostPlatforms=Win64' '-nop4' '-utf8output'
    if ($LASTEXITCODE -ne 0) { throw 'UE plugin build failed; installed version was not replaced' }
} finally {
    $env:uebp_LogFolder = $m53PreviousLog
}
if (-not $BuildOnly) {
    # Never replace modules loaded in an editor process.
    foreach ($m53Process in @(Get-Process UnrealEditor,UnrealEditor-Cmd -ErrorAction SilentlyContinue)) {
        foreach ($m53Module in $m53Process.Modules) {
            if ($m53Module.ModuleName -like '*AbuM53*') { throw 'Close editors using Abu M53 before installing' }
        }
    }
    $m53InstallArguments = @('install', '--directory', $m53Work, '--engine', $EngineDirectory)
    if ($ReplaceUnreleased) { $m53InstallArguments += '--replace-unreleased' }
    & $Python $m53Helper @m53InstallArguments
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed' }
    & $Python $m53Helper verify --engine $EngineDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Installed verification failed' }
}
