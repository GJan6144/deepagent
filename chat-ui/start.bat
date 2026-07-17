@echo off
setlocal enabledelayedexpansion

set "PROJECT_DIR=C:\Users\Administrator\Documents\deepagent\deepagents"
set "VENV_PYTHON=%PROJECT_DIR%\libs\deepagents\.venv\Scripts\python.exe"
set "CHAT_UI_DIR=%PROJECT_DIR%\chat-ui"

:: 必须在启动前设置 OPENAI_API_KEY 和 OPENAI_BASE_URL
:: 例如：
::   set OPENAI_API_KEY=你的deepseek_api_key
::   set OPENAI_BASE_URL=https://api.deepseek.com/v1

if "%OPENAI_API_KEY%"=="" (
    echo [ERROR] 未设置 OPENAI_API_KEY
    echo 请在终端中先执行:
    echo   set OPENAI_API_KEY=你的deepseek_api_key
    pause
    exit /b 1
)
if "%OPENAI_BASE_URL%"=="" set "OPENAI_BASE_URL=https://api.deepseek.com/v1"

:: Kill any existing process on port 8765
for /f "tokens=5" %%a in ('netstat -ano ^| find ":8765" ^| find "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo ====================================
echo   Deep Agents Chat UI
echo ====================================
echo   Server: http://localhost:8765
echo   Model:  deepseek-v4-flash
echo ====================================
echo.
"%VENV_PYTHON%" "%CHAT_UI_DIR%\server.py"
pause
