@echo off
setlocal enabledelayedexpansion

set "PROJECT_DIR=C:\Users\Administrator\Documents\deepagent\deepagents"
set "WRAPPER_SCRIPT=%PROJECT_DIR%\launch_dcode.py"
set "VENV_PYTHON=%PROJECT_DIR%\libs\code\.venv\Scripts\python.exe"

set "OPENAI_API_KEY=sk-af80f067547940dbb092d870956d5dbb"
set "OPENAI_BASE_URL=https://api.deepseek.com/v1"

echo [Deep Agents Code] Starting...
echo [Model] deepseek-v4-flash
echo.
"%VENV_PYTHON%" "%WRAPPER_SCRIPT%" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] dcode exit code: %ERRORLEVEL%
    pause
)
