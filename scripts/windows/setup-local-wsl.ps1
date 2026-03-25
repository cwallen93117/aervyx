param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Admin {
    if (Test-IsAdmin) {
        return
    }

    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-RepoRoot", "`"$RepoRoot`""
    )

    Write-Step "Requesting elevation for WSL and Docker Desktop setup"
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList | Out-Null
    exit 0
}

function Enable-FeatureIfNeeded {
    param([string]$FeatureName)

    $state = (Get-WindowsOptionalFeature -Online -FeatureName $FeatureName).State
    if ($state -eq "Enabled") {
        return $false
    }

    Write-Host "Enabling Windows feature: $FeatureName"
    dism.exe /online /enable-feature /featurename:$FeatureName /all /norestart | Out-Host
    return $true
}

function Test-WingetPackageInstalled {
    param([string]$PackageId)

    $result = & winget list --exact --id $PackageId 2>$null
    return ($LASTEXITCODE -eq 0 -and $result -notmatch "No installed package found")
}

function Install-WingetPackageIfMissing {
    param(
        [string]$PackageId,
        [switch]$Silent
    )

    if (Test-WingetPackageInstalled -PackageId $PackageId) {
        Write-Host "$PackageId already installed."
        return
    }

    Write-Host "Installing $PackageId via winget..."
    $args = @(
        "install",
        "--exact",
        "--id", $PackageId,
        "--accept-package-agreements",
        "--accept-source-agreements"
    )
    if ($Silent) {
        $args += "--silent"
    }
    & winget @args
}

function Ensure-EnvFile {
    param(
        [string]$Path,
        [string]$Template
    )

    if (-not (Test-Path $Path) -and (Test-Path $Template)) {
        Copy-Item $Template $Path
    }
}

Ensure-Admin

$needsReboot = $false

Write-Step "Enabling WSL platform features"
if (Enable-FeatureIfNeeded -FeatureName "Microsoft-Windows-Subsystem-Linux") { $needsReboot = $true }
if (Enable-FeatureIfNeeded -FeatureName "VirtualMachinePlatform") { $needsReboot = $true }

Write-Step "Installing Windows-side packages"
Install-WingetPackageIfMissing -PackageId "Microsoft.WSL"
Install-WingetPackageIfMissing -PackageId "Canonical.Ubuntu.2404"
Install-WingetPackageIfMissing -PackageId "Docker.DockerDesktop" -Silent

Write-Step "Preparing repo env files"
Ensure-EnvFile -Path (Join-Path $RepoRoot ".env") -Template (Join-Path $RepoRoot ".env.example")
Ensure-EnvFile -Path (Join-Path $RepoRoot "backend\.env") -Template (Join-Path $RepoRoot "backend\.env.example")
Ensure-EnvFile -Path (Join-Path $RepoRoot "frontend\.env.local") -Template (Join-Path $RepoRoot "frontend\.env.local.example")

$wslScriptDir = Join-Path $RepoRoot "scripts\wsl"
New-Item -ItemType Directory -Path $wslScriptDir -Force | Out-Null

$statusPath = Join-Path $RepoRoot "docs\windows-wsl-setup-status.txt"
New-Item -ItemType Directory -Path (Split-Path $statusPath -Parent) -Force | Out-Null

$message = @(
    "Aervyx local WSL2 setup has been staged.",
    "",
    "Repo root: $RepoRoot",
    "WSL package installed: $(Test-WingetPackageInstalled -PackageId 'Microsoft.WSL')",
    "Ubuntu 24.04 installed: $(Test-WingetPackageInstalled -PackageId 'Canonical.Ubuntu.2404')",
    "Docker Desktop installed: $(Test-WingetPackageInstalled -PackageId 'Docker.DockerDesktop')",
    "",
    "Next Windows-required steps:",
    "1. Reboot Windows if WSL or VirtualMachinePlatform was just enabled.",
    "2. Launch Ubuntu once from the Start menu and create the Linux user/password.",
    "3. Start Docker Desktop once and wait for it to report running.",
    "4. Run '.\\scripts\\windows\\finish-local-wsl.ps1' from an elevated PowerShell."
)
Set-Content -Path $statusPath -Value $message

Write-Step "Writing WSL finish script"
$finishScriptPath = Join-Path $PSScriptRoot "finish-local-wsl.ps1"
if (-not (Test-Path $finishScriptPath)) {
    throw "Missing finish script template at $finishScriptPath"
}

if ($needsReboot) {
    Write-Host ""
    Write-Host "Windows features were enabled. A reboot is required before WSL can be initialized." -ForegroundColor Yellow
    Write-Host "Status written to: $statusPath" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Windows-side prerequisites are staged. If Ubuntu and Docker Desktop were already initialized, run:" -ForegroundColor Green
Write-Host "  .\\scripts\\windows\\finish-local-wsl.ps1" -ForegroundColor Green
