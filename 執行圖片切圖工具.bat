@echo off
chcp 65001 >nul
call "%~dp0use_crm_crawler.bat"
if errorlevel 1 goto :end

cd /d "%~dp0tools"

echo 使用 Python：%PYTHON%
echo.

"%PYTHON%" image_resize_export.py
if errorlevel 1 (
    echo.
    echo 程式執行失敗，請確認 crm_crawler 環境可用。
)

:end
echo.
pause
