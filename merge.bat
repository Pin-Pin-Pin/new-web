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
echo   [1] dev  - 相對路徑改寫為 jsDelivr（稍後輸入 tag）
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
echo   [1] 僅 body   - new-free-web 全部頁面（貼 CMS）
echo   [2] 完整 HTML - landing-page 全部頁面
echo.
choice /C 12 /N /M "請按 1 或 2："
if errorlevel 2 (
  set "TARGET=html"
  set "TARGET_LABEL=完整 HTML → landing-page"
) else (
  set "TARGET=body"
  set "TARGET_LABEL=僅 body → new-free-web"
)

set "TAG="
if /i not "!MODE!"=="dev" goto :after_tag

echo.
echo 請輸入 jsDelivr 使用的 git tag
echo 例如：v1.1.3
set /p TAG="tag："
if "!TAG!"=="" (
  echo [ERROR] 未輸入 tag，已取消。
  pause
  exit /b 1
)
REM 去掉開頭的 @（若有）
if "!TAG:~0,1!"=="@" set "TAG=!TAG:~1!"
if "!TAG!"=="" (
  echo [ERROR] tag 不可為空，已取消。
  pause
  exit /b 1
)

:after_tag
echo.
if not "!TAG!"=="" (
  echo 已選擇：!MODE_LABEL! / !TARGET_LABEL! / tag=!TAG!
) else (
  echo 已選擇：!MODE_LABEL! / !TARGET_LABEL!
)
echo.
echo 開始合併...
echo.

if /i "!MODE!"=="dev" (
  node "%~dp0tools\merge.js" "!MODE!" "!TARGET!" "!TAG!"
) else (
  node "%~dp0tools\merge.js" "!MODE!" "!TARGET!"
)
set "EXITCODE=!ERRORLEVEL!"

echo.
if not "!EXITCODE!"=="0" (
  echo [ERROR] 合併失敗，exit code !EXITCODE!
) else (
  echo 完成。
)
pause
exit /b !EXITCODE!
