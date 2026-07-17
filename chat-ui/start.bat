@echo off
setlocal

set "PROJECT_DIR=C:\Users\Administrator\Documents\deepagent\deepagents"
set "VENV_PYTHON=%PROJECT_DIR%\libs\deepagents\.venv\Scripts\python.exe"
set "CHAT_UI_DIR=%PROJECT_DIR%\chat-ui"

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
echo Config loaded from: %CHAT_UI_DIR%\.env (if exists)
echo.
"%VENV_PYTHON%" "%CHAT_UI_DIR%\server.py"
pause
