@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
call "%~dp0use_crm_crawler.bat"
if errorlevel 1 goto :end

cd /d "%~dp0tools"

echo 使用 Python：%PYTHON%
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
