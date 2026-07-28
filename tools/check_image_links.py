#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CET Taiwan - HTML / CSS 圖檔連結檢查工具

功能：
  - 選擇資料夾與一張以上 HTML / CSS 檔案
  - 擷取 img / source / srcset / CSS url() 的圖檔連結
  - 本機相對路徑檢查檔案是否存在
  - 遠端 http(s) 連結以 GET（stream）檢查 HTTP 狀態碼（含 404；不依賴不可靠的 HEAD）
"""

from __future__ import annotations

import re
import sys
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog
from typing import Iterable
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".avif",
    ".bmp",
    ".ico",
    ".tif",
    ".tiff",
}

# CSS url(...)；略過 data: / # / 空值
CSS_URL_RE = re.compile(
    r"""url\(\s*(?:'([^']*)'|"([^"]*)"|([^'")\s]+))\s*\)""",
    re.IGNORECASE,
)

# srcset: "url 1x, url 480w"
SRCSET_ITEM_RE = re.compile(r"^\s*(\S+)")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 "
    "CET-ImageLinkChecker/1.0"
)
REQUEST_TIMEOUT = 12
MAX_WORKERS = 8


@dataclass(frozen=True)
class FoundLink:
    file: Path
    raw: str
    line: int | None = None
    context: str = ""


@dataclass
class CheckResult:
    link: FoundLink
    status: str  # ok / missing / http_error / skip / error
    detail: str = ""
    http_code: int | None = None


@dataclass
class Report:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def broken(self) -> list[CheckResult]:
        return [r for r in self.results if r.status in {"missing", "http_error"}]


def select_folder_and_files() -> tuple[Path, list[Path]]:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    folder = filedialog.askdirectory(title="選擇要檢查的資料夾")
    if not folder:
        root.destroy()
        return Path(), []

    files = filedialog.askopenfilenames(
        title="選擇 HTML / CSS 檔案（可多選）",
        initialdir=folder,
        filetypes=[
            ("HTML / CSS", "*.html;*.htm;*.css"),
            ("HTML", "*.html;*.htm"),
            ("CSS", "*.css"),
            ("所有檔案", "*.*"),
        ],
    )
    root.destroy()

    if not files:
        return Path(folder), []

    allowed = {".html", ".htm", ".css"}
    selected = [Path(f) for f in files if Path(f).suffix.lower() in allowed]
    return Path(folder), selected


def ask_site_base_url() -> str:
    print(
        "\n若檔案內有以 / 開頭的根路徑圖檔（例如 /sites/.../a.webp），"
        "請輸入網站根網址以便檢查；直接 Enter 則略過根路徑。"
    )
    print("範例：https://www.cet-taiwan.org")
    return input("> ").strip().rstrip("/")


def should_skip_url(url: str) -> bool:
    u = url.strip()
    if not u or u.startswith("#"):
        return True
    lower = u.lower()
    return lower.startswith(("data:", "javascript:", "mailto:", "tel:"))


def looks_like_image(url: str) -> bool:
    """遠端或無副檔名時保守視為圖檔；有副檔名則比對常見圖檔。"""
    path = urlparse(url).path
    suffix = Path(unquote(path)).suffix.lower()
    if not suffix:
        return True
    return suffix in IMAGE_EXTS


def parse_srcset(value: str) -> list[str]:
    urls: list[str] = []
    for part in value.split(","):
        m = SRCSET_ITEM_RE.match(part)
        if m:
            urls.append(m.group(1).strip())
    return urls


def find_line_number(text: str, needle: str) -> int | None:
    if not needle:
        return None
    idx = text.find(needle)
    if idx < 0:
        # 可能被 HTML entity / 空白影響，改找路徑檔名
        name = Path(urlparse(needle).path).name
        if name:
            idx = text.find(name)
    if idx < 0:
        return None
    return text.count("\n", 0, idx) + 1


def extract_from_html(path: Path) -> list[FoundLink]:
    text = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    found: list[FoundLink] = []
    seen: set[str] = set()

    def add(raw: str, context: str) -> None:
        raw = raw.strip()
        if should_skip_url(raw) or raw in seen:
            return
        if not looks_like_image(raw):
            return
        seen.add(raw)
        found.append(
            FoundLink(
                file=path,
                raw=raw,
                line=find_line_number(text, raw),
                context=context,
            )
        )

    for tag in soup.find_all(["img", "source", "image", "use"]):
        tag_name = tag.name or "?"
        for attr in ("src", "href", "data-src", "data-lazy-src", "poster"):
            val = tag.get(attr)
            if isinstance(val, str):
                add(val, f"<{tag_name} {attr}>")
        for attr in ("srcset", "data-srcset"):
            val = tag.get(attr)
            if isinstance(val, str):
                for u in parse_srcset(val):
                    add(u, f"<{tag_name} {attr}>")

    # style 內聯 background / url()
    for tag in soup.find_all(style=True):
        style = tag.get("style") or ""
        for m in CSS_URL_RE.finditer(style):
            add(next(g for g in m.groups() if g is not None), "inline style url()")

    # <style> 區塊
    for style_tag in soup.find_all("style"):
        css = style_tag.string or style_tag.get_text() or ""
        for m in CSS_URL_RE.finditer(css):
            add(next(g for g in m.groups() if g is not None), "<style> url()")

    return found


def extract_from_css(path: Path) -> list[FoundLink]:
    text = path.read_text(encoding="utf-8", errors="replace")
    found: list[FoundLink] = []
    seen: set[str] = set()

    for m in CSS_URL_RE.finditer(text):
        raw = next(g for g in m.groups() if g is not None).strip()
        if should_skip_url(raw) or raw in seen:
            continue
        if not looks_like_image(raw):
            continue
        seen.add(raw)
        line = text.count("\n", 0, m.start()) + 1
        found.append(FoundLink(file=path, raw=raw, line=line, context="css url()"))

    return found


def extract_links(path: Path) -> list[FoundLink]:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return extract_from_html(path)
    if suffix == ".css":
        return extract_from_css(path)
    return []


def resolve_target(
    link: FoundLink, site_base: str
) -> tuple[str, str | Path | None]:
    """
    回傳 (kind, target)
    kind: remote | local | skip
    """
    raw = link.raw.strip()
    parsed = urlparse(raw)

    if parsed.scheme in {"http", "https"}:
        return "remote", raw

    if parsed.scheme and parsed.scheme not in {"", "file"}:
        return "skip", None

    # 根路徑 /foo/bar.webp
    if raw.startswith("/"):
        if site_base:
            return "remote", site_base + raw
        return "skip", None

    # 相對路徑
    local = (link.file.parent / unquote(raw.split("?", 1)[0].split("#", 1)[0])).resolve()
    return "local", local


def check_remote(url: str, session: requests.Session) -> tuple[str, str, int | None]:
    """
    一律用 GET（stream）檢查。
    cet-taiwan.org 等主機對不存在的圖檔 HEAD 仍可能回 200 + Content-Length: 0，
    只有 GET 才會得到真實 404。
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    try:
        resp = session.get(
            url,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
            headers=headers,
            stream=True,
        )
        code = resp.status_code
        # 讀一點 body 確保連線完成狀態，再關掉避免下載整張圖
        try:
            next(resp.iter_content(chunk_size=64), None)
        finally:
            resp.close()

        if code == 404:
            return "http_error", "HTTP 404 Not Found", code
        if 200 <= code < 400:
            return "ok", f"HTTP {code}", code
        return "http_error", f"HTTP {code}", code
    except requests.RequestException as exc:
        return "error", f"連線失敗：{exc}", None


def check_link(
    link: FoundLink, site_base: str, session: requests.Session
) -> CheckResult:
    kind, target = resolve_target(link, site_base)

    if kind == "skip":
        if link.raw.startswith("/") and not site_base:
            return CheckResult(
                link=link,
                status="skip",
                detail="根路徑未提供網站根網址，已略過",
            )
        return CheckResult(link=link, status="skip", detail="非可檢查連結，已略過")

    if kind == "local":
        assert isinstance(target, Path)
        if target.is_file():
            return CheckResult(link=link, status="ok", detail=f"本機存在：{target}")
        return CheckResult(
            link=link,
            status="missing",
            detail=f"本機找不到檔案：{target}",
        )

    assert isinstance(target, str)
    status, detail, code = check_remote(target, session)
    return CheckResult(link=link, status=status, detail=detail, http_code=code)


def unique_links(links: Iterable[FoundLink]) -> list[FoundLink]:
    """相同檔案 + 相同 raw 只檢查一次（保留首次出現）。"""
    seen: set[tuple[str, str]] = set()
    out: list[FoundLink] = []
    for link in links:
        key = (str(link.file.resolve()), link.raw)
        if key in seen:
            continue
        seen.add(key)
        out.append(link)
    return out


def print_report(report: Report) -> None:
    total = len(report.results)
    ok = sum(1 for r in report.results if r.status == "ok")
    broken = report.broken
    skipped = [r for r in report.results if r.status == "skip"]
    errors = [r for r in report.results if r.status == "error"]

    print("\n" + "=" * 60)
    print("檢查結果摘要")
    print("=" * 60)
    print(f"  連結總數：{total}")
    print(f"  正常　　：{ok}")
    print(f"  異常　　：{len(broken)}")
    print(f"  略過　　：{len(skipped)}")
    print(f"  連線錯誤：{len(errors)}")

    if broken:
        print("\n--- 異常連結（404 / 本機缺失 / HTTP 錯誤）---")
        for r in broken:
            loc = f"{r.link.file.name}"
            if r.link.line:
                loc += f":{r.link.line}"
            print(f"\n  [{r.status}] {loc}")
            print(f"    連結：{r.link.raw}")
            if r.link.context:
                print(f"    來源：{r.link.context}")
            print(f"    說明：{r.detail}")

    if errors:
        print("\n--- 連線失敗 ---")
        for r in errors:
            loc = f"{r.link.file.name}"
            if r.link.line:
                loc += f":{r.link.line}"
            print(f"\n  {loc}")
            print(f"    連結：{r.link.raw}")
            print(f"    說明：{r.detail}")

    if skipped:
        print("\n--- 已略過 ---")
        for r in skipped:
            print(f"  · {r.link.file.name} → {r.link.raw}（{r.detail}）")

    if not broken and not errors:
        print("\n全部可檢查的圖檔連結皆正常。")


def main() -> None:
    print("CET Taiwan - HTML / CSS 圖檔連結檢查工具")
    print("-" * 40)

    folder, files = select_folder_and_files()
    if not folder:
        print("已取消選擇資料夾。")
        sys.exit(0)
    if not files:
        print("未選擇任何 HTML / CSS 檔案。")
        sys.exit(0)

    print(f"\n資料夾：{folder}")
    print(f"已選檔案（{len(files)}）：")
    for f in files:
        print(f"  · {f.name}")

    all_links: list[FoundLink] = []
    for f in files:
        try:
            links = extract_links(f)
        except OSError as exc:
            print(f"⚠ 無法讀取 {f.name}：{exc}", file=sys.stderr)
            continue
        print(f"  {f.name}：找到 {len(links)} 個圖檔連結")
        all_links.extend(links)

    all_links = unique_links(all_links)
    if not all_links:
        print("\n未找到任何圖檔連結。")
        sys.exit(0)

    need_base = any(lnk.raw.startswith("/") for lnk in all_links)
    site_base = ask_site_base_url() if need_base else ""

    print(f"\n開始檢查 {len(all_links)} 個連結…")
    session = requests.Session()
    report = Report()

    # 本機路徑可同步；遠端並行
    local_jobs: list[FoundLink] = []
    remote_jobs: list[FoundLink] = []
    for link in all_links:
        kind, _ = resolve_target(link, site_base)
        if kind == "remote":
            remote_jobs.append(link)
        else:
            local_jobs.append(link)

    for link in local_jobs:
        report.results.append(check_link(link, site_base, session))

    if remote_jobs:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(check_link, link, site_base, session): link
                for link in remote_jobs
            }
            done = 0
            for fut in as_completed(futures):
                report.results.append(fut.result())
                done += 1
                if done % 5 == 0 or done == len(remote_jobs):
                    print(f"  遠端進度：{done}/{len(remote_jobs)}")

    # 依檔名、行號排序，方便閱讀
    report.results.sort(
        key=lambda r: (
            str(r.link.file).lower(),
            r.link.line or 0,
            r.link.raw,
        )
    )
    print_report(report)

    if report.broken or any(r.status == "error" for r in report.results):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已中斷。")
        sys.exit(130)
