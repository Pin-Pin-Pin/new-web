#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
從指定的 HTML / CSS 檔案擷取圖片 URL 並下載。

支援：
  - HTML：img[src]、source[srcset]、inline style、data-* 屬性中的圖片
  - CSS：background-image 等 url(...) 語法
  - 相對路徑、-base-url- 佔位符
  - 自動略過 data: URI 與非圖片連結
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

RASTER_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tiff",
    ".tif",
    ".svg",
    ".ico",
    ".avif",
}

CSS_URL_RE = re.compile(
    r"""url\s*\(\s*(['"]?)([^'")]+)\1\s*\)""",
    re.IGNORECASE,
)

HTML_URL_ATTRS = ("src", "poster", "data-azat-image")
HTML_SRCSET_ATTRS = ("srcset", "data-srcset")

DEFAULT_BASE_URL = "https://www.cet-taiwan.org"
DEFAULT_FILES_DIR = "sites/cet-taiwan.org/files"


def replace_placeholders(url: str, base_url: str, files_dir: str) -> str:
    url = url.replace("-base-url-", base_url.rstrip("/"))
    url = url.replace("-files-directory-", files_dir.strip("/"))
    url = url.replace("-module-directory-", "modules")
    return url


def resolve_url(raw: str, base_path: Path, base_url: str, files_dir: str) -> str | None:
    raw = raw.strip().strip("\"'")
    if not raw or raw.startswith(("data:", "javascript:", "#", "mailto:")):
        return None

    raw = replace_placeholders(raw, base_url, files_dir)

    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith(("http://", "https://")):
        return raw
    if raw.startswith("/"):
        return base_url.rstrip("/") + raw

    return urljoin(base_path.as_uri() + "/", raw)


def parse_srcset(value: str) -> list[str]:
    urls: list[str] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        urls.append(part.split()[0])
    return urls


def extract_urls_from_css(css_text: str, css_path: Path, base_url: str, files_dir: str) -> set[str]:
    urls: set[str] = set()
    for match in CSS_URL_RE.finditer(css_text):
        resolved = resolve_url(match.group(2), css_path.parent, base_url, files_dir)
        if resolved:
            urls.add(resolved)
    return urls


def extract_urls_from_html(
    html_text: str, html_path: Path, base_url: str, files_dir: str
) -> set[str]:
    urls: set[str] = set()
    soup = BeautifulSoup(html_text, "html.parser")

    for tag in soup.find_all(True):
        for attr in HTML_URL_ATTRS:
            value = tag.get(attr)
            if value:
                resolved = resolve_url(value, html_path.parent, base_url, files_dir)
                if resolved:
                    urls.add(resolved)

        for attr in HTML_SRCSET_ATTRS:
            value = tag.get(attr)
            if value:
                for item in parse_srcset(value):
                    resolved = resolve_url(item, html_path.parent, base_url, files_dir)
                    if resolved:
                        urls.add(resolved)

        style = tag.get("style") or tag.get("data-azat-style")
        if style:
            for match in CSS_URL_RE.finditer(style):
                resolved = resolve_url(match.group(2), html_path.parent, base_url, files_dir)
                if resolved:
                    urls.add(resolved)

    for match in CSS_URL_RE.finditer(html_text):
        resolved = resolve_url(match.group(2), html_path.parent, base_url, files_dir)
        if resolved:
            urls.add(resolved)

    return urls


def is_image_url(url: str) -> bool:
    path = urlparse(url).path
    name = unquote(Path(path).name)
    if not name or name in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}:
        return False
    return Path(name).suffix.lower() in RASTER_EXTENSIONS


def filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = unquote(Path(path).name)
    return name or "image"


def unique_dest_path(dest_dir: Path, filename: str, url: str) -> Path:
    dest = dest_dir / filename
    if dest.exists():
        return dest

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    query = urlparse(url).query
    if query:
        fid_match = re.search(r"fid=(\d+)", query)
        if fid_match:
            alt = f"{stem}_fid{fid_match.group(1)}{suffix}"
            alt_path = dest_dir / alt
            if not alt_path.exists():
                return alt_path

    counter = 2
    while dest.exists():
        dest = dest_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    return dest


def collect_image_urls(
    html_files: list[Path],
    css_files: list[Path],
    base_url: str,
    files_dir: str,
    include_linked_css: bool,
) -> set[str]:
    urls: set[str] = set()

    for html_path in html_files:
        text = html_path.read_text(encoding="utf-8")
        urls.update(extract_urls_from_html(text, html_path, base_url, files_dir))

        if include_linked_css:
            soup = BeautifulSoup(text, "html.parser")
            for link in soup.find_all("link", rel=True):
                rel = link.get("rel") or []
                if "stylesheet" not in [r.lower() for r in rel]:
                    continue
                href = link.get("href")
                if not href or href.startswith("http"):
                    continue
                css_path = (html_path.parent / href).resolve()
                if css_path.is_file() and css_path not in css_files:
                    css_files.append(css_path)

    for css_path in css_files:
        text = css_path.read_text(encoding="utf-8")
        urls.update(extract_urls_from_css(text, css_path, base_url, files_dir))

    return {url for url in urls if is_image_url(url)}


def download_image(url: str, dest: Path, session: requests.Session) -> bool:
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except requests.RequestException as exc:
        print(f"  [錯誤] 下載失敗 {url}: {exc}", file=sys.stderr)
        return False


def resolve_input_paths(names: list[str], label: str) -> list[Path]:
    paths: list[Path] = []
    for name in names:
        path = Path(name)
        if not path.is_file():
            raise FileNotFoundError(f"找不到 {label} 檔案: {name}")
        paths.append(path.resolve())
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="從 HTML / CSS 擷取圖片 URL 並下載到指定資料夾"
    )
    parser.add_argument(
        "--html",
        nargs="*",
        default=[],
        help="HTML 檔案路徑（可指定多個）",
    )
    parser.add_argument(
        "--css",
        nargs="*",
        default=[],
        help="CSS 檔案路徑（可指定多個）",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="下載資料夾（預設：第一個 HTML 檔名，或 images/）",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"取代 -base-url- 佔位符（預設：{DEFAULT_BASE_URL}）",
    )
    parser.add_argument(
        "--files-dir",
        default=DEFAULT_FILES_DIR,
        help=f"取代 -files-directory- 佔位符（預設：{DEFAULT_FILES_DIR}）",
    )
    parser.add_argument(
        "--no-linked-css",
        action="store_true",
        help="不要自動讀取 HTML 中 link[rel=stylesheet] 引用的本地 CSS",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出將下載的 URL，不實際下載",
    )
    args = parser.parse_args()

    html_names = list(args.html)
    css_names = list(args.css)

    if not html_names and not css_names:
        html_input = input("請輸入 HTML 檔案路徑（多個以空格分隔，可留空）: ").strip()
        css_input = input("請輸入 CSS 檔案路徑（多個以空格分隔，可留空）: ").strip()
        html_names = html_input.split() if html_input else []
        css_names = css_input.split() if css_input else []

    if not html_names and not css_names:
        print("請至少指定一個 HTML 或 CSS 檔案。", file=sys.stderr)
        sys.exit(1)

    try:
        html_files = resolve_input_paths(html_names, "HTML")
        css_files = resolve_input_paths(css_names, "CSS")
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    image_urls = sorted(
        collect_image_urls(
            html_files,
            css_files,
            args.base_url,
            args.files_dir,
            include_linked_css=not args.no_linked_css,
        )
    )

    if not image_urls:
        print("未找到可下載的圖片 URL。")
        return

    if args.output:
        output_dir = Path(args.output).resolve()
    elif html_files:
        output_dir = html_files[0].parent / f"{html_files[0].stem}-images"
    else:
        output_dir = Path.cwd() / "images"

    print(f"找到 {len(image_urls)} 個圖片 URL")
    print(f"輸出資料夾: {output_dir}")

    if args.dry_run:
        for url in image_urls:
            print(f"  {filename_from_url(url)}  ←  {url}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "download_images/1.0"})

    ok = 0
    skipped = 0
    failed = 0

    for url in image_urls:
        filename = filename_from_url(url)
        dest = unique_dest_path(output_dir, filename, url)

        if dest.exists():
            print(f"  已存在: {dest.name}")
            skipped += 1
            continue

        print(f"  下載: {dest.name}")
        if download_image(url, dest, session):
            ok += 1
        else:
            failed += 1

    print(f"\n完成。成功 {ok}、已存在 {skipped}、失敗 {failed}")


if __name__ == "__main__":
    main()
