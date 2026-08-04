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
echo   CSS 選擇器加上 #main
echo ========================================
echo.
echo 請選擇處理範圍：
echo   [1] body - 處理 new-free-web 底下所有 .css
echo   [2] html - 處理 landing-page 底下所有 .css
echo.
echo 輸出會寫成同資料夾的 *_scoped.css（不覆寫原檔）
echo 已有 #main 前綴的選擇器會略過
echo 舊前綴 #main-content 會自動改成 #main
echo.
choice /C 12 /N /M "請按 1 或 2："
if errorlevel 2 (
  set "TARGET=html"
  set "TARGET_LABEL=html → landing-page"
) else (
  set "TARGET=body"
  set "TARGET_LABEL=body → new-free-web"
)

echo.
echo 已選擇：!TARGET_LABEL!
echo.
echo 開始處理...
echo.

node "%~dp0tools\scope-css.js" "!TARGET!"
set "EXITCODE=!ERRORLEVEL!"

echo.
if not "!EXITCODE!"=="0" (
  echo [ERROR] 處理失敗，exit code !EXITCODE!
) else (
  echo 完成。
)
pause
exit /b !EXITCODE!
