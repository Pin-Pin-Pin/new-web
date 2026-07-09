@echo off
chcp 65001 >nul
cd /d "%~dp0tools"

python image_resize_export.py
if errorlevel 1 (
    echo.
    echo 程式執行失敗，請確認已安裝 Python 並加入 PATH。
)

echo.
pause
