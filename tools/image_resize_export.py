#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CET Taiwan - 圖片尺寸輸出工具

功能：
  - 選擇資料夾與一張以上 PNG 圖片
  - 依圖片類型輸出多尺寸 JPG（magick）與 WebP（cwebp）
  - WebP：先以 ImageMagick 縮圖，再以 cwebp 編碼（不使用 cwebp -resize）
  - WebP 可選有損（預設）或無損壓縮；透明 PNG 轉 WebP 仍保留透明度
  - 不放大；原圖小於最小規格時僅格式轉換
  - 輸出至 jpg-{quality} / webp-{lossy|lossless}-{q} 子資料夾
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog

JPG_DEFAULT_QUALITY = 82
WEBP_DEFAULT_Q = 80
WEBP_OPTIONS = [90, 85, 80, 75]

SCRIPT_DIR = Path(__file__).resolve().parent
TYPES_FILE = SCRIPT_DIR / "image_types.json"


@dataclass
class ProcessResult:
    filename: str
    orig_width: int
    output_widths: list[int] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    has_transparency: bool = False


def load_image_types() -> dict:
    if not TYPES_FILE.is_file():
        print(f"❌ 找不到尺寸表：{TYPES_FILE}", file=sys.stderr)
        sys.exit(1)
    with TYPES_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def check_dependencies() -> None:
    missing = []
    for cmd in ("magick", "cwebp"):
        if not shutil.which(cmd):
            missing.append(cmd)
    if missing:
        print(f"❌ 找不到必要工具：{', '.join(missing)}", file=sys.stderr)
        print("   請確認 ImageMagick（magick）與 libwebp（cwebp）已安裝並加入 PATH。", file=sys.stderr)
        sys.exit(1)


def get_image_width(image_path: Path) -> int:
    result = subprocess.run(
        ["magick", "identify", "-format", "%w", str(image_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "無法讀取圖片寬度")
    return int(result.stdout.strip())


def has_transparency(image_path: Path) -> bool:
    """檢查 PNG 是否含透明或半透明像素。"""
    result = subprocess.run(
        ["magick", "identify", "-format", "%[opaque]", str(image_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    return result.stdout.strip().lower() == "false"


TRANSPARENT_PNG_NOTE = "⚠ 透明 PNG：JPG 已填白底，WebP 保留透明度"


def get_output_widths(type_widths: list[int], orig_width: int) -> tuple[list[int], list[str], list[str]]:
    """回傳 (輸出寬度列表, 略過原因, 備註)。"""
    sorted_widths = sorted(type_widths)
    min_spec = sorted_widths[0]
    max_spec = sorted_widths[-1]
    skipped = [f"略過 {w}px：不放大" for w in sorted_widths if w > orig_width]
    notes: list[str] = []

    if orig_width < min_spec:
        notes.append(f"原圖 {orig_width}px 小於最小規格 {min_spec}px，僅格式轉換")
        return [orig_width], skipped, notes

    outputs = [w for w in sorted_widths if w <= orig_width]

    if orig_width not in sorted_widths and orig_width < max_spec:
        outputs.append(orig_width)
        outputs = sorted(set(outputs))
        notes.append(f"額外輸出原圖寬度 {orig_width}px（格式轉換）")

    return outputs, skipped, notes


def export_jpg(
    src: Path,
    dest: Path,
    target_width: int,
    orig_width: int,
    quality: int,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["magick", str(src), "-strip", "-background", "white", "-alpha", "remove", "-alpha", "off"]
    if target_width < orig_width:
        cmd.extend(["-resize", f"{target_width}x"])
    cmd.extend(["-quality", str(quality), str(dest)])

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "JPG 轉換失敗")


def build_cwebp_cmd(src: Path, dest: Path, q: int, lossless: bool) -> list[str]:
    """組出 cwebp 指令；有損與無損皆會保留 PNG 透明度。"""
    cmd = ["cwebp"]
    if lossless:
        cmd.append("-lossless")
    cmd.extend(["-q", str(q), str(src), "-o", str(dest)])
    return cmd


def export_webp(
    src: Path,
    dest: Path,
    target_width: int,
    orig_width: int,
    q: int,
    lossless: bool = False,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)

    # 需縮圖時先用 ImageMagick 縮（Lanczos 等較佳濾鏡），再交 cwebp 編碼；
    # 不需縮圖則直接從原圖編碼。透明度由 cwebp 保留（有損／無損皆可）。
    if target_width < orig_width:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_png = Path(tmpdir) / "resized.png"
            resize_cmd = [
                "magick",
                str(src),
                "-strip",
                "-resize",
                f"{target_width}x",
                str(tmp_png),
            ]
            resize_result = subprocess.run(
                resize_cmd, capture_output=True, text=True, check=False
            )
            if resize_result.returncode != 0:
                raise RuntimeError(
                    resize_result.stderr.strip() or "WebP 縮圖失敗（ImageMagick）"
                )

            encode_cmd = build_cwebp_cmd(tmp_png, dest, q, lossless)
            encode_result = subprocess.run(
                encode_cmd, capture_output=True, text=True, check=False
            )
            if encode_result.returncode != 0:
                raise RuntimeError(
                    encode_result.stderr.strip() or "WebP 轉換失敗"
                )
        return

    cmd = build_cwebp_cmd(src, dest, q, lossless)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "WebP 轉換失敗")


def process_image(
    src_path: Path,
    type_widths: list[int],
    jpg_dir: Path,
    webp_dir: Path,
    jpg_quality: int,
    webp_q: int,
    webp_lossless: bool = False,
) -> ProcessResult:
    filename = src_path.name
    stem = src_path.stem
    result = ProcessResult(filename=filename, orig_width=0)

    try:
        orig_width = get_image_width(src_path)
        result.orig_width = orig_width
        result.has_transparency = has_transparency(src_path)
        widths, skipped, size_notes = get_output_widths(type_widths, orig_width)
        result.output_widths = widths
        result.skipped = skipped
        result.notes = size_notes
        if result.has_transparency:
            result.notes.append(TRANSPARENT_PNG_NOTE)

        for width in widths:
            jpg_name = f"{stem}-{width}.jpg"
            webp_name = f"{stem}-{width}.webp"
            export_jpg(src_path, jpg_dir / jpg_name, width, orig_width, jpg_quality)
            export_webp(
                src_path,
                webp_dir / webp_name,
                width,
                orig_width,
                webp_q,
                webp_lossless,
            )
    except Exception as exc:
        result.errors.append(str(exc))

    return result


def select_folder_and_files() -> tuple[Path, list[Path]]:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    folder = filedialog.askdirectory(title="選擇圖片資料夾")
    if not folder:
        root.destroy()
        return Path(), []

    folder_path = Path(folder)
    files = filedialog.askopenfilenames(
        title="選擇 PNG 圖片（可多選）",
        initialdir=folder,
        filetypes=[("PNG 圖片", "*.png"), ("所有檔案", "*.*")],
    )
    root.destroy()

    if not files:
        return folder_path, []

    png_files = [Path(f) for f in files if Path(f).suffix.lower() == ".png"]
    return folder_path, png_files


def choose_image_type(types: dict) -> tuple[str, str, list[int]]:
    keys = list(types.keys())
    custom_option = len(keys) + 1
    print("\n請選擇圖片類型：")
    for i, key in enumerate(keys, 1):
        label = types[key]["label"]
        widths = " / ".join(str(w) for w in types[key]["widths"])
        print(f"  {i}. {label}（{widths}）")
    print(f"  {custom_option}. 自訂尺寸")

    while True:
        raw = input("\n> ").strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(keys):
                key = keys[idx]
                return key, types[key]["label"], types[key]["widths"]
            if int(raw) == custom_option:
                widths = ask_custom_widths()
                return "custom", "自訂尺寸", widths
        if raw in types:
            return raw, types[raw]["label"], types[raw]["widths"]
        if raw in {"custom", "自訂", "自訂尺寸"}:
            widths = ask_custom_widths()
            return "custom", "自訂尺寸", widths
        print("❌ 無效選項，請重新輸入編號。")


def ask_custom_widths() -> list[int]:
    print("\n請輸入輸出寬度（可多個，以空格、逗號或 / 分隔）")
    print("例如：480 800 1600")
    while True:
        raw = input("\n> ").strip()
        if not raw:
            print("❌ 請至少輸入一個寬度。")
            continue

        parts = [p.strip() for p in raw.replace("/", " ").replace(",", " ").split() if p.strip()]
        widths: list[int] = []
        invalid = False
        for part in parts:
            if not part.isdigit():
                invalid = True
                break
            value = int(part)
            if value <= 0:
                invalid = True
                break
            widths.append(value)

        if invalid or not widths:
            print("❌ 請輸入有效的正整數寬度。")
            continue

        widths = sorted(set(widths))
        confirm = " / ".join(str(w) for w in widths)
        print(f"   將使用：{confirm}")
        return widths


def ask_jpg_quality() -> int:
    raw = input(f"\nJPG quality（預設 {JPG_DEFAULT_QUALITY}）\n> ").strip()
    if not raw:
        return JPG_DEFAULT_QUALITY
    try:
        value = int(raw)
        if 1 <= value <= 100:
            return value
    except ValueError:
        pass
    print(f"⚠️  輸入無效，使用預設值 {JPG_DEFAULT_QUALITY}")
    return JPG_DEFAULT_QUALITY


def ask_webp_lossless() -> bool:
    """選擇 WebP 壓縮方式。回傳 True = 無損；空白或無效則預設有損。"""
    raw = input("\nWebP 壓縮（1=有損 / 2=無損，預設有損）\n> ").strip().lower()
    if not raw or raw in {"1", "lossy", "有損"}:
        return False
    if raw in {"2", "lossless", "無損"}:
        return True
    print("⚠️  輸入無效，使用有損壓縮")
    return False


def ask_webp_q(*, lossless: bool = False) -> int:
    if lossless:
        # 無損時 -q 代表壓縮程度（愈高愈慢、檔案通常愈小），非畫質
        raw = input(
            f"\nWebP 無損壓縮程度 q（預設 {WEBP_DEFAULT_Q}，0–100）\n> "
        ).strip()
    else:
        options_text = " / ".join(str(q) for q in WEBP_OPTIONS)
        raw = input(
            f"\nWebP q（預設 {WEBP_DEFAULT_Q}，可選 {options_text}）\n> "
        ).strip()
    if not raw:
        return WEBP_DEFAULT_Q
    try:
        value = int(raw)
        if not lossless and value in WEBP_OPTIONS:
            return value
        if 0 <= value <= 100:
            if not lossless and value not in WEBP_OPTIONS:
                print(f"⚠️  {value} 不在建議選項內，仍將使用此數值。")
            return value
    except ValueError:
        pass
    print(f"⚠️  輸入無效，使用預設值 {WEBP_DEFAULT_Q}")
    return WEBP_DEFAULT_Q


def print_summary(results: list[ProcessResult], jpg_dir: Path, webp_dir: Path) -> None:
    print("\n" + "=" * 88)
    print(f"{'檔名':<28} {'原寬':>6} {'輸出尺寸':<22} {'略過 / 備註'}")
    print("-" * 88)

    for r in results:
        outputs = ", ".join(f"{w}px" for w in r.output_widths) if r.output_widths else "—"
        extra = r.skipped + r.notes + r.errors
        extra_text = "；".join(extra) if extra else "—"
        print(f"{r.filename:<28} {r.orig_width:>6} {outputs:<22} {extra_text}")

    print("=" * 88)
    success = sum(1 for r in results if not r.errors)
    transparent_count = sum(1 for r in results if r.has_transparency)
    print(f"\n✅ 完成 {success}/{len(results)} 張")
    if transparent_count:
        print(f"⚠  其中 {transparent_count} 張為透明 PNG，JPG 已填白底，WebP 保留透明度")
    print(f"   JPG  → {jpg_dir}")
    print(f"   WebP → {webp_dir}")


def main() -> None:
    print("=" * 50)
    print("  CET Taiwan 圖片尺寸輸出工具")
    print("=" * 50)

    check_dependencies()
    types = load_image_types()

    print("\n📁 請在視窗中選擇資料夾與 PNG 圖片…")
    folder_path, png_files = select_folder_and_files()

    if not folder_path or not png_files:
        print("❌ 未選擇資料夾或圖片，程式結束。")
        sys.exit(1)

    invalid = [f for f in png_files if f.suffix.lower() != ".png"]
    if invalid:
        print("❌ 僅支援 PNG 輸入，請重新選擇。")
        sys.exit(1)

    type_key, type_label, type_widths = choose_image_type(types)
    jpg_quality = ask_jpg_quality()
    webp_lossless = ask_webp_lossless()
    webp_q = ask_webp_q(lossless=webp_lossless)

    jpg_dir = folder_path / f"jpg-{jpg_quality}"
    webp_mode_tag = "lossless" if webp_lossless else "lossy"
    webp_dir = folder_path / f"webp-{webp_mode_tag}-{webp_q}"
    jpg_dir.mkdir(exist_ok=True)
    webp_dir.mkdir(exist_ok=True)

    print("\n" + "=" * 50)
    print(f"資料夾：{folder_path}")
    print(f"類型：{type_label}")
    print(f"輸出寬度：{' / '.join(str(w) for w in type_widths)}")
    print(f"圖片數：{len(png_files)}")
    print(f"JPG quality：{jpg_quality}")
    print(f"WebP：{'無損' if webp_lossless else '有損'}（q={webp_q}）")
    print("開始處理…\n")

    results: list[ProcessResult] = []
    max_workers = min(len(png_files), os.cpu_count() or 4)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_image,
                src,
                type_widths,
                jpg_dir,
                webp_dir,
                jpg_quality,
                webp_q,
                webp_lossless,
            ): src
            for src in png_files
        }
        for future in as_completed(futures):
            src = futures[future]
            result = future.result()
            results.append(result)
            if result.errors:
                print(f"  ❌  {result.filename}：{'; '.join(result.errors)}")
            else:
                widths = ", ".join(str(w) for w in result.output_widths)
                print(f"  ✅  {result.filename}（{result.orig_width}px → {widths}）")

    results.sort(key=lambda r: r.filename.lower())
    print_summary(results, jpg_dir, webp_dir)


if __name__ == "__main__":
    main()
