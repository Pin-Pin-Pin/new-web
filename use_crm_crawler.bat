@echo off
rem 專案使用的 Python 虛擬環境（conda: crm_crawler）
set "PYTHON=C:\Users\USER\miniconda3\envs\crm_crawler\python.exe"

if not exist "%PYTHON%" (
    set "PYTHON=C:\Users\Hsuan\miniconda3\envs\crm_crawler\python.exe"
)

if not exist "%PYTHON%" (
    echo 找不到 crm_crawler 環境：
    echo   C:\Users\USER\miniconda3\envs\crm_crawler\python.exe
    echo   C:\Users\Hsuan\miniconda3\envs\crm_crawler\python.exe
    exit /b 1
)
