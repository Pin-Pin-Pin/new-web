#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CET Taiwan - 圖片處理工具（Step 1）
功能：
  - 掃描指定資料夾中的圖片
  - 縮放至寬度 1200px（等比例）
  - 解析度設為 75 dpi，品質 75
  - 轉存為 WebP 格式
  - 依日期+序號重新命名（如 20260413-001.webp）
  - 原始檔保留不刪除

執行完畢後，再用 image_uploader.py 上傳。
"""

import os
from pathlib import Path
import arrow
from PIL import Image

# ─────────────────────────────────────────────
# 支援的輸入格式
# ─────────────────────────────────────────────
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}

# ─────────────────────────────────────────────
# 互動式設定
# ─────────────────────────────────────────────
print("=" * 50)
print("  CET Taiwan 圖片處理工具  (Step 1)")
print("=" * 50)

# 1. 來源資料夾
default_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
folder_input = input(f"\n📁 圖片來源資料夾（直接 Enter 使用預設：{default_folder}）\n> ").strip()
SOURCE_FOLDER = folder_input if folder_input else default_folder

if not os.path.isdir(SOURCE_FOLDER):
    print(f"❌ 找不到資料夾：{SOURCE_FOLDER}")
    exit(1)

# 2. 輸出資料夾（預設同來源）
out_folder_input = input(f"\n📂 輸出資料夾（直接 Enter 輸出至同一資料夾）\n> ").strip()
OUTPUT_FOLDER = out_folder_input if out_folder_input else SOURCE_FOLDER

if not os.path.isdir(OUTPUT_FOLDER):
    os.makedirs(OUTPUT_FOLDER)
    print(f"   已建立輸出資料夾：{OUTPUT_FOLDER}")

# 3. 起始編號
start_num_input = input("\n🔢 序號從幾號開始？（預設：1）\n> ").strip()
try:
    START_NUM = int(start_num_input) if start_num_input else 1
except ValueError:
    print("❌ 請輸入數字。")
    exit(1)

# 4. 日期前綴（預設今天）
today = arrow.now().format("YYYYMMDD")
date_input = input(f"\n📅 檔名日期前綴（直接 Enter 使用今天：{today}）\n> ").strip()
DATE_PREFIX = date_input if date_input else today

print("\n" + "=" * 50)

# ─────────────────────────────────────────────
# 取得所有支援的圖片（依檔名排序，排除已命名的 webp）
# ─────────────────────────────────────────────
def get_source_images(folder):
    files = []
    for f in sorted(os.listdir(folder)):
        p = Path(f)
        if p.suffix.lower() in SUPPORTED_EXT:
            files.append(os.path.join(folder, f))
    return files

source_files = get_source_images(SOURCE_FOLDER)

if not source_files:
    print("⚠️  資料夾中找不到任何支援的圖片（jpg/jpeg/png/gif/bmp/tiff）。")
    exit(0)

print(f"\n找到 {len(source_files)} 張圖片，開始處理...\n")

# ─────────────────────────────────────────────
# 處理圖片
# ─────────────────────────────────────────────
output_files = []
count = START_NUM

for src_path in source_files:
    src_filename = os.path.basename(src_path)
    try:
        img = Image.open(src_path)

        # 色彩模式轉換（WebP 支援 RGB / RGBA）
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        # 縮放至寬度 1200px（等比例）
        orig_w, orig_h = img.size
        if orig_w > 1200:
            new_h = int(orig_h * 1200 / orig_w)
            img = img.resize((1200, new_h), Image.LANCZOS)

        # 輸出路徑
        num_str = str(count).zfill(3)
        out_filename = f"{DATE_PREFIX}-{num_str}.webp"
        out_path = os.path.join(OUTPUT_FOLDER, out_filename)

        # 儲存 WebP
        img.save(out_path, "WEBP", quality=75, dpi=(75, 75))
        print(f"  ✅  {src_filename}  →  {out_filename}")
        output_files.append(out_filename)
        count += 1

    except Exception as e:
        print(f"  ❌  處理失敗：{src_filename}  ({e})")

print(f"\n✅ 處理完成！共轉換 {len(output_files)} 張圖片。")
print(f"   輸出資料夾：{OUTPUT_FOLDER}")
print("\n📌 接下來請執行 image_uploader.py 進行上傳。")
