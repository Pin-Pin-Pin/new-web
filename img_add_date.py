#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CET Taiwan - 圖片檔名加日期前綴工具
功能：
  - 掃描指定資料夾中的圖片
  - 於檔名前面加上日期前綴（如 20260413-photo.jpg）
  - 原始檔直接重新命名，不複製、不轉檔
"""

import os
import re
from pathlib import Path
import arrow

# ─────────────────────────────────────────────
# 支援的格式
# ─────────────────────────────────────────────
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}

# 已含 YYYYMMDD- 前綴的檔名（避免重複加前綴）
DATE_PREFIX_PATTERN = re.compile(r"^\d{8}-")

# ─────────────────────────────────────────────
# 互動式設定
# ─────────────────────────────────────────────
print("=" * 50)
print("  CET Taiwan 圖片檔名加日期前綴工具")
print("=" * 50)

# 1. 目標資料夾
default_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
folder_input = input(f"\n📁 圖片資料夾（直接 Enter 使用預設：{default_folder}）\n> ").strip()
TARGET_FOLDER = folder_input if folder_input else default_folder

if not os.path.isdir(TARGET_FOLDER):
    print(f"❌ 找不到資料夾：{TARGET_FOLDER}")
    exit(1)

# 2. 日期前綴（預設今天）
today = arrow.now().format("YYYYMMDD")
date_input = input(f"\n📅 檔名日期前綴（直接 Enter 使用今天：{today}）\n> ").strip()
DATE_PREFIX = date_input if date_input else today

if not re.fullmatch(r"\d{8}", DATE_PREFIX):
    print("❌ 日期前綴格式須為 YYYYMMDD（8 位數字）。")
    exit(1)

print("\n" + "=" * 50)

# ─────────────────────────────────────────────
# 取得所有支援的圖片（依檔名排序）
# ─────────────────────────────────────────────
def get_image_files(folder):
    files = []
    for f in sorted(os.listdir(folder)):
        p = Path(f)
        if p.suffix.lower() in SUPPORTED_EXT:
            files.append(f)
    return files


def build_new_filename(filename, date_prefix):
    return f"{date_prefix}-{filename}"


image_files = get_image_files(TARGET_FOLDER)

if not image_files:
    print("⚠️  資料夾中找不到任何支援的圖片（jpg/jpeg/png/gif/bmp/tiff/webp）。")
    exit(0)

print(f"\n找到 {len(image_files)} 張圖片，開始重新命名...\n")

# ─────────────────────────────────────────────
# 重新命名
# ─────────────────────────────────────────────
renamed_count = 0
skipped_count = 0

for filename in image_files:
    if DATE_PREFIX_PATTERN.match(filename):
        print(f"  ⏭️  略過（已有日期前綴）：{filename}")
        skipped_count += 1
        continue

    new_filename = build_new_filename(filename, DATE_PREFIX)
    src_path = os.path.join(TARGET_FOLDER, filename)
    dst_path = os.path.join(TARGET_FOLDER, new_filename)

    if os.path.exists(dst_path):
        print(f"  ❌  略過（目標檔名已存在）：{filename}  →  {new_filename}")
        skipped_count += 1
        continue

    try:
        os.rename(src_path, dst_path)
        print(f"  ✅  {filename}  →  {new_filename}")
        renamed_count += 1
    except OSError as e:
        print(f"  ❌  重新命名失敗：{filename}  ({e})")

print(f"\n✅ 處理完成！共重新命名 {renamed_count} 張圖片。")
if skipped_count:
    print(f"   略過 {skipped_count} 張圖片。")
print(f"   資料夾：{TARGET_FOLDER}")
