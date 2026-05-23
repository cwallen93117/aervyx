param(
  [string]$ProfileOverlay = "$PSScriptRoot\profiles\aervyx_profiles.local.yaml"
)

$ErrorActionPreference = "Stop"
$Name = "AervyxMeshtasticProvisioner"
$TempResources = Join-Path $PSScriptRoot ".build_resources"
$DistDir = Join-Path $PSScriptRoot "dist"
$BuildDir = Join-Path $PSScriptRoot "build"

python -m pip install -r "$PSScriptRoot\requirements.txt"

if (Test-Path $TempResources) {
  Remove-Item -Recurse -Force -LiteralPath $TempResources
}
New-Item -ItemType Directory -Force -Path $TempResources | Out-Null
Copy-Item "$PSScriptRoot\provisioner\resources\*" $TempResources
if (Test-Path $ProfileOverlay) {
  Copy-Item $ProfileOverlay (Join-Path $TempResources "aervyx_profiles.local.yaml")
  Write-Host "Included local fleet profile overlay."
} else {
  Write-Host "No local fleet profile overlay found; EXE will contain placeholders only."
}

python -m PyInstaller `
  --noconfirm `
  --windowed `
  --name $Name `
  --distpath $DistDir `
  --workpath $BuildDir `
  --add-data "$TempResources;provisioner/resources" `
  "$PSScriptRoot\provisioner\__main__.py"

$ZipPath = Join-Path $DistDir "$Name-0.1.1-win-x64.zip"
if (Test-Path $ZipPath) {
  Remove-Item -Force -LiteralPath $ZipPath
}
Compress-Archive -Path (Join-Path $DistDir $Name) -DestinationPath $ZipPath
Get-FileHash -Algorithm SHA256 $ZipPath | Format-List
Write-Host "Built $ZipPath"
