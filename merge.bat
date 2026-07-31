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
echo   HTML Merge Tool
echo ========================================
echo.

REM ---- 選擇模式 ----
echo 請選擇輸出模式：
echo   [1] dev  - 相對路徑改寫為 jsDelivr，使用最新 tag
echo   [2] 正式 - 本地 CSS/JS 內嵌進 HTML
echo.
choice /C 12 /N /M "請按 1 或 2："
if errorlevel 2 (
  set "MODE=prod"
  set "MODE_LABEL=正式"
) else (
  set "MODE=dev"
  set "MODE_LABEL=dev"
)

echo.
echo 請選擇輸出範圍：
echo   [1] 僅 body   - 只輸出 body，適合貼 CMS
echo   [2] 完整 HTML - 保留 head
echo.
choice /C 12 /N /M "請按 1 或 2："
if errorlevel 2 (
  set "TARGET=html"
  set "TARGET_LABEL=完整 HTML"
) else (
  set "TARGET=body"
  set "TARGET_LABEL=僅 body"
)

echo.
echo 已選擇：!MODE_LABEL! / !TARGET_LABEL!
echo.
echo 即將開啟資料夾視窗
echo 起始位置是 merge.bat 所在目錄，請再手動進入頁面資料夾
echo 例如 landing-page\general-donate 或 new-free-web\volunteer
echo 不要選專案根目錄本身
echo.

REM ---- 資料夾選擇器：起始 = merge.bat 所在資料夾 ----
set "FOLDER="
set "STARTDIR=%~dp0"
if "%STARTDIR:~-1%"=="\" set "STARTDIR=%STARTDIR:~0,-1%"
set "PICKFILE=%TEMP%\cet-merge-folder.txt"
if exist "%PICKFILE%" del /f /q "%PICKFILE%" >nul 2>&1

powershell -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\pick-folder.ps1" -StartDir "%STARTDIR%" -OutFile "%PICKFILE%"
if errorlevel 1 goto :no_folder
if not exist "%PICKFILE%" goto :no_folder

set /p FOLDER=<"%PICKFILE%"
del /f /q "%PICKFILE%" >nul 2>&1

if not defined FOLDER goto :no_folder

echo 資料夾：!FOLDER!
echo.
echo 開始合併...
echo.

node "%~dp0tools\merge.js" "!FOLDER!" "!MODE!" "!TARGET!"
set "EXITCODE=!ERRORLEVEL!"

echo.
if not "!EXITCODE!"=="0" (
  echo [ERROR] 合併失敗，exit code !EXITCODE!
) else (
  echo 完成。
)
pause
exit /b !EXITCODE!

:no_folder
echo [ERROR] 未選擇資料夾，已取消。
echo 若沒有跳出選資料夾視窗，請再試一次或告訴開發者。
pause
exit /b 1
