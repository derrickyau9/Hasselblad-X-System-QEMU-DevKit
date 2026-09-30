param(
    [Parameter(Mandatory=$true)][string]$NdkRoot,
    [Parameter(Mandatory=$true)][string]$FirmwareLibraries
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Compiler = Join-Path $NdkRoot 'toolchains\llvm\prebuilt\windows-x86_64\bin\clang.exe'
foreach ($Name in @('mini_compositor','dbus_launcher','mock_services')) {
    $Source = Join-Path $Root "devkit\guest\$Name.c"
    $Output = Join-Path $Root "devkit\helpers\$Name"
    $Extra = @()
    if ($Name -eq 'mini_compositor') { $Extra = @("-L$FirmwareLibraries",'-lweston','-Wl,--allow-shlib-undefined') }
    if ($Name -eq 'mock_services') { $Extra = @("-L$FirmwareLibraries",'-ldbus') }
    & $Compiler '--target=aarch64-linux-android28' -O2 -fPIE -pie $Source -o $Output @Extra
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $Name" }
}
