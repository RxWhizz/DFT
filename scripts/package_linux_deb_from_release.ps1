$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$version = if ($args.Count -ge 1) { $args[0] } else { "0.3.0" }
$packageName = "perovowl-dft-monitor"
$deb = Join-Path $root "dist\$packageName-$version-linux-amd64.deb"

$wslRoot = $root -replace "\\", "/"
$wslRoot = $wslRoot -replace "^([A-Za-z]):", { "/mnt/" + $_.Groups[1].Value.ToLower() }

wsl bash -lc "cd '$wslRoot' && bash scripts/package_linux_deb_from_release.sh"

Get-Item $deb | Select-Object FullName, Length, LastWriteTime
