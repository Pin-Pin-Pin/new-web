#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CET Taiwan - 圖片上傳工具（Step 2）
功能：
  - 掃描指定資料夾中的圖片（WebP 或 JPG/PNG，由使用者選擇）
  - 開啟 Firefox，導向登入頁面
  - 自動填入帳號密碼後，等待使用者手動輸入驗證碼並登入
  - 登入成功後，逐一上傳圖片至 IMCE 檔案管理器

上傳 WebP 前，請先執行 image_processor.py 完成轉檔。
"""

import os
import time
import getpass
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from webdriver_manager.firefox import GeckoDriverManager

# ─────────────────────────────────────────────
# 支援的上傳格式
# ─────────────────────────────────────────────
FORMAT_OPTIONS = {
    "1": ({".webp"}, "WebP"),
    "2": ({".jpg", ".jpeg", ".png"}, "JPG / PNG"),
}

# ─────────────────────────────────────────────
# 互動式設定
# ─────────────────────────────────────────────
print("=" * 50)
print("  CET Taiwan 圖片上傳工具  (Step 2)")
print("=" * 50)

# 1. 圖片資料夾
default_folder = "D:/網頁/cet-change/img/farm-img"
folder_input = input(f"\n📁 圖片資料夾路徑（直接 Enter 使用預設：{default_folder}）\n> ").strip()
SOURCE_FOLDER = folder_input if folder_input else default_folder

if not os.path.isdir(SOURCE_FOLDER):
    print(f"❌ 找不到資料夾：{SOURCE_FOLDER}")
    exit(1)

# 2. 上傳格式
print("\n📷 請選擇要上傳的圖片格式：")
print("   1. WebP 圖片 (.webp)")
print("   2. JPG / PNG 圖片 (.jpg, .jpeg, .png)")
format_input = input("> ").strip()
if format_input not in FORMAT_OPTIONS:
    print("❌ 請輸入 1 或 2。")
    exit(1)

SUPPORTED_EXT, FORMAT_LABEL = FORMAT_OPTIONS[format_input]

# 3. 帳號密碼
print("\n🔐 請輸入網站登入資訊：")
USERNAME = input("   帳號：").strip()
PASSWORD = getpass.getpass("   密碼（不會顯示）：")

print("\n" + "=" * 50)

# ─────────────────────────────────────────────
# 掃描上傳目標圖片（依檔名排序）
# ─────────────────────────────────────────────
def get_upload_files(folder):
    files = []
    for f in sorted(os.listdir(folder)):
        if Path(f).suffix.lower() in SUPPORTED_EXT:
            files.append(os.path.join(folder, f))
    return files

upload_files = get_upload_files(SOURCE_FOLDER)

if not upload_files:
    print(f"❌ 資料夾中找不到任何可上傳的 {FORMAT_LABEL} 圖片。")
    exit(0)

# ─────────────────────────────────────────────
# 確認上傳清單
# ─────────────────────────────────────────────
print(f"\n📋 找到以下 {len(upload_files)} 個 {FORMAT_LABEL} 檔案：")
for f in upload_files:
    print(f"   {os.path.basename(f)}")

confirm = input(f"\n確認開始上傳這 {len(upload_files)} 張圖片？(y/n)\n> ").strip().lower()
if confirm != "y":
    print("已取消上傳。")
    exit(0)

# ─────────────────────────────────────────────
# 啟動瀏覽器並登入
# ─────────────────────────────────────────────
print("\n🌐 啟動 Firefox 瀏覽器...\n")
service = Service(executable_path=GeckoDriverManager().install())
driver = webdriver.Firefox(service=service)

driver.get("https://cet-taiwan.org/user")
time.sleep(2)

# 填入帳號密碼
try:
    ac = driver.find_element(By.ID, "edit-name")
    pw = driver.find_element(By.ID, "edit-pass")
    login_btn = driver.find_element(By.ID, "edit-submit")

    ac.send_keys(USERNAME)
    time.sleep(0.3)
    pw.send_keys(PASSWORD)
    time.sleep(0.3)
except Exception as e:
    print(f"❌ 找不到登入欄位：{e}")
    driver.quit()
    exit(1)

# ─────────────────────────────────────────────
# 等待使用者手動輸入驗證碼並按下登入
# ─────────────────────────────────────────────
print("=" * 50)
print("⚠️  請在瀏覽器中手動輸入「驗證碼」後，按下登入按鈕。")
print("   登入成功後，回到這個視窗按 Enter 繼續上傳。")
print("=" * 50)
input("\n✅ 已登入完成，按 Enter 繼續... ")

# ─────────────────────────────────────────────
# 開啟 IMCE 檔案管理器
# ─────────────────────────────────────────────
print("\n📂 開啟檔案管理器...")
imce_url = (
    "https://www.cet-taiwan.org/index.php?q=imce"
    "&app=ckeditor|sendto@ckeditor_setFile|"
    "&CKEditorFuncNum=104"
)
driver.get(imce_url)
time.sleep(3)

# 展開上傳表單
try:
    upload_toggle = driver.find_element(By.NAME, "upload")
    upload_toggle.click()
    time.sleep(2)
except Exception as e:
    print(f"❌ 找不到上傳按鈕：{e}")
    driver.quit()
    exit(1)

# ─────────────────────────────────────────────
# 逐一上傳圖片
# ─────────────────────────────────────────────
total = len(upload_files)
success = 0
failed = []

for idx, filepath in enumerate(upload_files, start=1):
    filename = os.path.basename(filepath)
    abs_path = os.path.abspath(filepath)
    print(f"  📤 ({idx}/{total}) 上傳中：{filename}")

    try:
        file_input = driver.find_element(By.NAME, "files[imce]")
        file_input.send_keys(abs_path)
        time.sleep(2)

        submit_btn = driver.find_element(By.NAME, "op")
        submit_btn.click()
        time.sleep(4)

        success += 1
    except Exception as e:
        print(f"     ❌ 上傳失敗：{e}")
        failed.append(filename)

# ─────────────────────────────────────────────
# 結果摘要
# ─────────────────────────────────────────────
print("\n" + "=" * 50)
print(f"✅ 上傳完成！成功：{success} 張 / 共 {total} 張")
if failed:
    print(f"❌ 失敗的檔案：")
    for f in failed:
        print(f"   - {f}")
print("=" * 50)

driver.quit()
