param(
  [Parameter(Mandatory = $true)]
  [string]$Prompt,

  [string[]]$Files = @(),

  [switch]$GuiHeavy,

  [switch]$Json
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$claude = Get-Command claude -ErrorAction Stop

$rolePrompt = if ($GuiHeavy) {
@"
You are acting as the Claude GUI decision-maker for the Aervyx frontend.

This is a GUI-heavy review. Focus on:
- layout structure
- visual hierarchy
- interaction design
- alternative implementation approaches
- practical repo-fit tradeoffs

Give:
1. recommended approach
2. one meaningful alternative
3. implementation notes for the existing codebase
4. major risks or tradeoffs

You are setting the preferred GUI direction. Codex will implement and integrate it unless a hard repo constraint requires adaptation.
"@
} else {
@"
You are acting as the Claude frontend advisor for the Aervyx frontend.

This is a non-GUI or mixed frontend review. Focus on:
- repo-fit implementation advice
- state/data flow
- UX impact if relevant
- risks and alternatives when they matter

Give:
1. recommended approach
2. implementation notes
3. notable risks

Codex remains the final decision-maker and implementation owner for non-GUI frontend work.
"@
}

$filesSection = if ($Files.Count -gt 0) {
  $normalized = $Files | ForEach-Object {
    if ([System.IO.Path]::IsPathRooted($_)) {
      $_
    } else {
      Join-Path $repoRoot $_
    }
  }
  "Relevant files:`n" + (($normalized | ForEach-Object { "- $_" }) -join "`n")
} else {
  "Relevant files: none specified."
}

$fullPrompt = @"
$filesSection

Frontend request:
$Prompt

Please keep your response concise and implementation-oriented.
"@

$args = @(
  "--print",
  "--permission-mode", "plan",
  "--add-dir", $repoRoot,
  "--append-system-prompt", $rolePrompt
)

if ($Json) {
  $args += @("--output-format", "json")
}

$args += $fullPrompt

& $claude.Source @args
