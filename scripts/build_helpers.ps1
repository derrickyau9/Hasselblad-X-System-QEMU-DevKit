param(
    [Parameter(Mandatory=$true)][string]$NdkRoot,
    [Parameter(Mandatory=$true)][string]$FirmwareLibraries,
    [ValidateSet('arm64','arm32')][string]$Architecture = 'arm64'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Compiler = Join-Path $NdkRoot 'toolchains\llvm\prebuilt\windows-x86_64\bin\clang.exe'
$Target = if ($Architecture -eq 'arm32') { 'armv7a-linux-androideabi23' } else { 'aarch64-linux-android28' }
$OutputDirectory = Join-Path $Root 'devkit\helpers'
if ($Architecture -eq 'arm32') { $OutputDirectory = Join-Path $OutputDirectory 'arm32' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
foreach ($Name in @('mini_compositor','dbus_launcher','mock_services')) {
    $Source = Join-Path $Root "devkit\guest\$Name.c"
    $Output = Join-Path $OutputDirectory $Name
    $Extra = @()
    if ($Name -eq 'mini_compositor') { $Extra = @("-L$FirmwareLibraries",'-lweston','-Wl,--allow-shlib-undefined') }
    if ($Name -eq 'mini_compositor' -and $Architecture -eq 'arm32') { $Extra = @("-L$FirmwareLibraries",'-lwayland-server','-Wl,--allow-shlib-undefined') }
    if ($Name -eq 'mock_services') { $Extra = @("-L$FirmwareLibraries",'-ldbus') }
    & $Compiler "--target=$Target" -O2 -fPIE -pie $Source -o $Output @Extra
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $Name" }
}
if ($Architecture -eq 'arm32') {
    & $Compiler "--target=$Target" -O2 -shared -fPIC (Join-Path $Root 'devkit\guest\ion_compat.c') -o (Join-Path $OutputDirectory 'ion_compat.so')
    if ($LASTEXITCODE -ne 0) { throw 'Build failed: ion_compat' }
}
