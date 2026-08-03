@echo off
chcp 65001 >nul
call "%~dp0use_crm_crawler.bat"
if errorlevel 1 goto :end

cd /d "%~dp0tools"

echo 使用 Python：%PYTHON%
echo.

"%PYTHON%" check_image_links.py
if errorlevel 1 (
    echo.
    echo 檢查完成：發現異常連結或連線錯誤。
)

:end
echo.
pause
