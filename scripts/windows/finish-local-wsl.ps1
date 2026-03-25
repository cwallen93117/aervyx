param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$Distro = "Ubuntu-24.04"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Wsl {
    param([string]$Command)
    & wsl.exe -d $Distro -- bash -lc $Command
}

Write-Step "Checking WSL distro availability"
$distroList = & wsl.exe -l -q 2>$null
if ($LASTEXITCODE -ne 0 -or $distroList -notcontains $Distro) {
    throw "WSL distro '$Distro' is not ready yet. Launch Ubuntu once from the Start menu to finish first-run setup."
}

Write-Step "Setting WSL defaults"
& wsl.exe --set-default-version 2
& wsl.exe --set-default $Distro

Write-Step "Creating Linux-side workspace"
$repoRootWsl = "/mnt/" + $RepoRoot.Substring(0,1).ToLower() + ($RepoRoot.Substring(2) -replace "\\","/")
$bootstrapScriptWsl = "$repoRootWsl/scripts/wsl/bootstrap-aervyx.sh"
$command = "chmod +x ""$bootstrapScriptWsl"" && ""$bootstrapScriptWsl"" ""$repoRootWsl"""
Invoke-Wsl -Command $command

Write-Step "Verifying local endpoints"
Start-Sleep -Seconds 5
try { Invoke-WebRequest -UseBasicParsing http://localhost:3000/login | Out-Null } catch { }
try { Invoke-WebRequest -UseBasicParsing http://localhost:8000/health | Out-Null } catch { }

Write-Host ""
Write-Host "Aervyx local WSL stack bootstrap has been kicked off." -ForegroundColor Green
Write-Host "Frontend: http://localhost:3000/login" -ForegroundColor Green
Write-Host "Backend:  http://localhost:8000/health" -ForegroundColor Green
