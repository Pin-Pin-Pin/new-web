@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] 找不到 node，請先安裝 Node.js 並確保在 PATH 中。
  pause
  exit /b 1
)

echo.
echo ========================================
echo   CSS 選擇器加上 #main-content
echo ========================================
echo.
echo 即將開啟檔案視窗，請選擇要處理的 .css
echo 輸出會寫成同資料夾的 *_scoped.css（不覆寫原檔）
echo 已有 #main-content 前綴的選擇器會略過
echo.

set "FILE="
set "STARTDIR=%~dp0"
if "%STARTDIR:~-1%"=="\" set "STARTDIR=%STARTDIR:~0,-1%"
set "PICKFILE=%TEMP%\cet-scope-css-file.txt"
if exist "%PICKFILE%" del /f /q "%PICKFILE%" >nul 2>&1

powershell -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\pick-file.ps1" -StartDir "%STARTDIR%" -OutFile "%PICKFILE%"
if errorlevel 1 goto :no_file
if not exist "%PICKFILE%" goto :no_file

set /p FILE=<"%PICKFILE%"
del /f /q "%PICKFILE%" >nul 2>&1

if not defined FILE goto :no_file

echo 檔案：!FILE!
echo.
echo 開始處理...
echo.

node "%~dp0tools\scope-css.js" "!FILE!"
set "EXITCODE=!ERRORLEVEL!"

echo.
if not "!EXITCODE!"=="0" (
  echo [ERROR] 處理失敗，exit code !EXITCODE!
) else (
  echo 完成。
)
pause
exit /b !EXITCODE!

:no_file
echo [ERROR] 未選擇檔案，已取消。
pause
exit /b 1
