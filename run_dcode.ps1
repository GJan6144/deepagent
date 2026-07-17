@"
# Deep Agents Code (dcode) launcher with DeepSeek v4 Flash
# Uses Python wrapper to properly register provider profile
$projectDir = "C:\Users\Administrator\Documents\deepagent\deepagents"
$venvPython = Join-Path $projectDir "libs\code\.venv\Scripts\python.exe"
$wrapperScript = Join-Path $projectDir "launch_dcode.py"

$env:OPENAI_API_KEY = "sk-af80f067547940dbb092d870956d5dbb"
$env:OPENAI_BASE_URL = "https://api.deepseek.com/v1"

Write-Host "[Deep Agents Code] Starting..."
Write-Host "[Model] deepseek-v4-flash"
Write-Host ""

# Pass all user arguments to the Python wrapper
if ($args.Count -gt 0) {
    & $venvPython $wrapperScript $args
} else {
    & $venvPython $wrapperScript
}

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] dcode exit code: $LASTEXITCODE"
    Read-Host "Press Enter to exit"
}
"@