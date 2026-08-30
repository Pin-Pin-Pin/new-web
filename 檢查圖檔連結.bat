@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
call "%~dp0use_crm_crawler.bat"
if errorlevel 1 goto :end

cd /d "%~dp0tools"

echo 使用 Python：%PYTHON%
echo.
echo 將檢查 HTML / CSS / JS 內的所有連結（含 script 字串中的網址）。
echo 接著會跳出視窗，請選擇資料夾；會自動檢查其中（含子資料夾）所有 HTML / CSS / JS。
echo 會略過檔名為 *_merge.html、*_scoped.css 的檔案。
echo cet-taiwan.org 會以 guest / cet 驗證，並略過過期的 HTTPS 憑證。
echo 官網連結會逐筆檢查，每 10 筆隨機暫停約 1–4 秒，降低被封鎖的機會。
echo 不需要手動輸入路徑或逐一選檔。
echo.

echo ========================================
echo   相對路徑的網站根網址
echo ========================================
echo.
echo   遇到 /sites/... 這類相對網址時，會接上此網址再檢查。
echo.
echo   [1] https://dev.cet-taiwan.org  （預設，直接 Enter）
echo   [2] https://www.cet-taiwan.org
echo   [3] 自行輸入
echo.
set "BASE_CHOICE="
set /p BASE_CHOICE="請輸入 1、2 或 3："

set "SITE_BASE=https://dev.cet-taiwan.org"
if "!BASE_CHOICE!"=="2" set "SITE_BASE=https://www.cet-taiwan.org"
if "!BASE_CHOICE!"=="3" (
  echo.
  set "CUSTOM_BASE="
  set /p CUSTOM_BASE="請輸入網址："
  if not "!CUSTOM_BASE!"=="" (
    set "SITE_BASE=!CUSTOM_BASE!"
  ) else (
    echo 未輸入，改用預設：https://dev.cet-taiwan.org
  )
)

echo.
echo 已選擇 base 網址：!SITE_BASE!
echo.

"%PYTHON%" check_image_links.py --base-url "!SITE_BASE!"
if errorlevel 1 (
    echo.
    echo 檢查完成：發現異常連結或連線錯誤。
)

:end
echo.
pause
