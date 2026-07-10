$source = Join-Path $PSScriptRoot "specimpact"
$target = Join-Path $HOME ".gemini\config\plugins\specimpact"
New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
Write-Output "Installed SpecImpact Antigravity plugin to $target"
