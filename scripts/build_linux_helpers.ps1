param(
    [Parameter(Mandatory=$true)][string]$NdkRoot,
    [Parameter(Mandatory=$true)][string]$Sysroot
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$CompatRoot = (Resolve-Path -LiteralPath $Sysroot).Path
$Compiler = Join-Path $NdkRoot 'toolchains\llvm\prebuilt\windows-x86_64\bin\clang.exe'
$Output = Join-Path $Root 'devkit\helpers\linux-arm32'
New-Item -ItemType Directory -Force -Path $Output | Out-Null
foreach ($Helper in @('mini_compositor','mock_services')) {
    $Library = if ($Helper -eq 'mini_compositor') { '-l:libwayland-server.so.0' } else { '-l:libdbus-1.so.3' }
    & $Compiler --target=arm-linux-gnueabihf "--sysroot=$CompatRoot" -isystem "$CompatRoot\usr\include\arm-linux-gnueabihf" -O2 -fPIE -pie -fuse-ld=lld -nostdlib `
        "$CompatRoot\usr\lib\arm-linux-gnueabihf\Scrt1.o" "$CompatRoot\usr\lib\arm-linux-gnueabihf\crti.o" (Join-Path $Root "devkit\guest\$Helper.c") `
        "-L$CompatRoot\usr\lib\arm-linux-gnueabihf" "-L$CompatRoot\lib\arm-linux-gnueabihf" '-Wl,-dynamic-linker,/lib/ld-linux-armhf.so.3' '-Wl,--allow-shlib-undefined' `
        $Library -l:libc.so.6 -l:libgcc_s.so.1 -l:libc_nonshared.a "$CompatRoot\usr\lib\arm-linux-gnueabihf\crtn.o" -o (Join-Path $Output $Helper)
    if ($LASTEXITCODE -ne 0) { throw "Linux helper build failed: $Helper" }
}
