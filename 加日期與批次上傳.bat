@echo off
chcp 65001 >nul
call "%~dp0use_crm_crawler.bat"
if errorlevel 1 goto :end

cd /d "%~dp0tools\old"
set CET_BATCH_UPLOAD=1

echo 使用 Python：%PYTHON%
echo.

echo ================================================
echo   Step 1：圖片檔名加日期前綴
echo ================================================
"%PYTHON%" img_add_date.py
if errorlevel 1 (
    echo.
    echo Step 1 執行失敗，已中止，未執行上傳。
    goto :end
)

echo.
echo ================================================
echo   Step 2：批次上傳圖片
echo ================================================
"%PYTHON%" image_uploader.py
if errorlevel 1 (
    echo.
    echo Step 2 執行失敗，請確認 crm_crawler 環境與相關套件。
)

:end
echo.
pause
