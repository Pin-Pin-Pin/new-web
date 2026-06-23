#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CET Taiwan - NETivCRM 圖片批次上傳工具
功能：
  1. 自動壓縮圖片至寬度 1200px、解析度 75dpi，並轉成 WebP 格式
  2. 自動依日期+序號重新命名（如 20260413-001.webp）
  3. 透過 Selenium 自動上傳至官網檔案管理器
  4. 帳號密碼、資料夾路徑、序號起始值均於執行時互動輸入
"""

import os
import time
import getpass
import glob
from pathlib import Path

from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from webdriver_manager.firefox import GeckoDriverManager
import arrow

# ─────────────────────────────────────────────
# 互動式設定
# ─────────────────────────────────────────────

print("=" * 50)
print("  CET Taiwan 圖片上傳工具")
print("=" * 50)

# 1. 選擇來源資料夾
default_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
folder_input = input(f"\n📁 圖片來源資料夾路徑（直接 Enter 使用預設：{default_folder}）\n> ").strip()
SOURCE_FOLDER = folder_input if folder_input else default_folder

if not os.path.isdir(SOURCE_FOLDER):
    print(f"❌ 找不到資料夾：{SOURCE_FOLDER}")
    exit(1)

# 2. 起始編號
start_num_input = input("\n🔢 上傳序號從幾號開始？（預設：1）\n> ").strip()
try:
    START_NUM = int(start_num_input) if start_num_input else 1
except ValueError:
    print("❌ 請輸入數字。")
    exit(1)

# 3. 是否處理圖片（壓縮 + 轉 WebP + 重新命名）
process_input = input("\n🖼️  是否要壓縮圖片並轉成 WebP 格式？(y/n，預設：y）\n> ").strip().lower()
DO_PROCESS = process_input != "n"

# 4. 上傳目標資料夾（NETiCRM 上的使用者資料夾代號，通常是 u400 等）
upload_folder_input = input("\n🌐 上傳目標資料夾代號（預設：u400）\n> ").strip()
UPLOAD_FOLDER = upload_folder_input if upload_folder_input else "u400"

# 5. 帳號密碼（不顯示在終端機）
print("\n🔐 請輸入網站登入資訊：")
USERNAME = input("   帳號：").strip()
PASSWORD = getpass.getpass("   密碼：")

print("\n" + "=" * 50)

# ─────────────────────────────────────────────
# 支援的圖片格式
# ─────────────────────────────────────────────
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}

def get_image_files(folder):
    """取得資料夾中所有支援的圖片檔案，依檔名排序。"""
    files = []
    for f in sorted(os.listdir(folder)):
        if Path(f).suffix.lower() in SUPPORTED_EXT:
            files.append(os.path.join(folder, f))
    return files

# ─────────────────────────────────────────────
# 圖片處理：壓縮 + 轉 WebP + 重新命名
# ─────────────────────────────────────────────

today = arrow.now().format("YYYYMMDD")

def process_images(folder, start_num):
    """
    將資料夾中的圖片：
    - 縮放至寬度 1200px（高度等比例縮放）
    - 解析度設為 75 dpi
    - 轉存為 WebP 格式
    - 重新命名為 YYYYMMDD-NNN.webp
    輸出檔案存在同一資料夾，原始檔保留。
    回傳：處理後的 WebP 檔案路徑列表。
    """
    source_files = get_image_files(folder)
    if not source_files:
        print("⚠️  找不到任何圖片檔案。")
        return []

    output_files = []
    count = start_num

    for src_path in source_files:
        src_filename = os.path.basename(src_path)
        # 跳過已是依規則命名的 webp（避免重複處理）
        if src_filename.endswith(".webp") and len(src_filename) == 16:  # YYYYMMDD-NNN.webp
            continue

        try:
            img = Image.open(src_path)

            # 轉換色彩模式（WebP 不支援 RGBA 以外的特殊模式）
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

            # 縮放至寬度 1200px（等比例）
            original_w, original_h = img.size
            if original_w > 1200:
                new_h = int(original_h * 1200 / original_w)
                img = img.resize((1200, new_h), Image.LANCZOS)

            # 輸出檔名
            num_str = str(count).zfill(3)
            out_filename = f"{today}-{num_str}.webp"
            out_path = os.path.join(folder, out_filename)

            # 儲存為 WebP，品質對應解析度 75
            img.save(out_path, "WEBP", quality=75, dpi=(75, 75))
            print(f"  ✅ {src_filename}  →  {out_filename}")
            output_files.append(out_path)
            count += 1

        except Exception as e:
            print(f"  ❌ 處理失敗：{src_filename}  ({e})")

    print(f"\n✅ 圖片處理完成，共 {len(output_files)} 張。\n")
    return output_files


# ─────────────────────────────────────────────
# 執行圖片處理（依使用者選擇）
# ─────────────────────────────────────────────

if DO_PROCESS:
    print("🔄 開始處理圖片...\n")
    upload_files = process_images(SOURCE_FOLDER, START_NUM)
    if not upload_files:
        print("沒有可上傳的圖片，程式結束。")
        exit(0)
else:
    print("⏭️  跳過圖片處理，直接掃描現有 WebP 檔案...\n")
    # 只取已有的 webp 檔，依序號排序
    all_files = get_image_files(SOURCE_FOLDER)
    upload_files = [f for f in all_files if Path(f).suffix.lower() == ".webp"]
    if not upload_files:
        # 沒有 webp 就取全部支援格式
        upload_files = all_files
    if not upload_files:
        print("❌ 資料夾中沒有找到任何圖片，程式結束。")
        exit(0)
    print(f"  找到 {len(upload_files)} 個圖片檔案準備上傳。\n")

# ─────────────────────────────────────────────
# 確認上傳
# ─────────────────────────────────────────────

print("📋 即將上傳的檔案：")
for f in upload_files:
    print(f"   {os.path.basename(f)}")

confirm = input(f"\n共 {len(upload_files)} 張，確認開始上傳？(y/n）\n> ").strip().lower()
if confirm != "y":
    print("已取消上傳。")
    exit(0)

# ─────────────────────────────────────────────
# Selenium 自動上傳
# ─────────────────────────────────────────────

print("\n🌐 啟動瀏覽器...\n")
service = Service(executable_path=GeckoDriverManager().install())
driver = webdriver.Firefox(service=service)

# 登入
driver.get("https://cet-taiwan.org/user")
time.sleep(2)

ac = driver.find_element(By.ID, "edit-name")
pw = driver.find_element(By.ID, "edit-pass")
login_btn = driver.find_element(By.ID, "edit-submit")

ac.send_keys(USERNAME)
time.sleep(0.4)
pw.send_keys(PASSWORD)
time.sleep(0.4)
login_btn.click()

print("⏳ 等待登入完成...")
time.sleep(10)

# 開啟檔案管理器
imce_url = (
    f"https://www.cet-taiwan.org/index.php?q=imce"
    f"&app=ckeditor|sendto@ckeditor_setFile|"
    f"&CKEditorFuncNum=104"
)
driver.get(imce_url)
time.sleep(3)

# 點擊「上傳」按鈕（展開上傳表單）
upload1 = driver.find_element(By.NAME, "upload")
upload1.click()
time.sleep(2)

# 逐一上傳圖片
total = len(upload_files)
for idx, filepath in enumerate(upload_files, start=1):
    filename = os.path.basename(filepath)
    abs_path = os.path.abspath(filepath)
    print(f"  📤 上傳中 ({idx}/{total})：{filename}")

    try:
        upload2 = driver.find_element(By.NAME, "files[imce]")
        upload2.send_keys(abs_path)
        time.sleep(2)
        upload3 = driver.find_element(By.NAME, "op")
        upload3.click()
        time.sleep(4)
    except Exception as e:
        print(f"     ❌ 上傳失敗：{e}")

print("\n✅ 所有圖片上傳完成！")
driver.quit()
