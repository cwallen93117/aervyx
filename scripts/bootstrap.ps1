param(
    [switch]$WindowsWsl
)

if ($WindowsWsl) {
    & "$PSScriptRoot\windows\setup-local-wsl.ps1"
    exit $LASTEXITCODE
}

Write-Host "Use '.\\scripts\\bootstrap.ps1 -WindowsWsl' to prepare the local WSL2 + Docker Desktop environment for Aervyx."
