#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CET Taiwan - HTML / CSS / JS 連結檢查工具

功能：
  - 以視窗選擇資料夾，自動檢查其中（含子資料夾）所有 HTML / CSS / JS
  - 擷取 href / src / srcset / poster / action、CSS url()、@import、
    script 與 JS 字串中的連結
  - 本機相對路徑（../img/...、../share-css/...）檢查檔案是否存在
  - 根路徑相對網址（/sites/...）接上 --base-url 後以 GET 檢查
  - 遠端 http(s) 連結以 GET（stream）檢查 HTTP 狀態碼（含 404；不依賴不可靠的 HEAD）
"""

from __future__ import annotations

import argparse
import random
import re
import sys
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog
from typing import Iterable
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.exceptions import InsecureRequestWarning
from urllib3.util.retry import Retry
import urllib3.util.connection as urllib3_connection

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
# Windows 上若優先走 IPv6，cet-taiwan.org 常會連線逾時；瀏覽器會改走 IPv4。
urllib3_connection.HAS_IPV6 = False

# HTML 常見網址屬性（不只圖檔）
URL_ATTRS = (
    "href",
    "src",
    "data-src",
    "data-lazy-src",
    "data-href",
    "poster",
    "action",
    "cite",
    "data-azat-image",
)

SRCSET_ATTRS = ("srcset", "data-srcset")
# 僅用來預連線，根網址 GET 常回 404（例如 fonts.gstatic.com）
CONNECTION_HINT_RELS = {"preconnect", "dns-prefetch"}

# CSS url(...)；略過 data: / # / 空值
CSS_URL_RE = re.compile(
    r"""url\(\s*(?:'([^']*)'|"([^"]*)"|([^'")\s]+))\s*\)""",
    re.IGNORECASE,
)

# @import "file.css" / @import 'file.css'（url() 形式已由 CSS_URL_RE 涵蓋）
CSS_IMPORT_RE = re.compile(
    r"""@import\s+(?:'([^']*)'|"([^"]*)")""",
    re.IGNORECASE,
)

# srcset: "url 1x, url 480w"
SRCSET_ITEM_RE = re.compile(r"^\s*(\S+)")

# JS / <script> 字串與註解中的網址
JS_STRING_RE = re.compile(r"""(['"])((?:\\.|(?!\1).)*)\1""")
JS_TEMPLATE_RE = re.compile(r"`([^`]*?)`")
JS_HTTP_RE = re.compile(r"https?://[^\s'\"<>)\]}>]+", re.IGNORECASE)
IMAGE_BASE_ASSIGN_RE = re.compile(
    r"""(?:var|let|const)\s+IMAGE_BASE\s*=\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
IMAGE_BASE_CONCAT_RE = re.compile(
    r"""IMAGE_BASE\s*\+\s*([^+;\n]+?)\s*\+\s*['"]([^'"]+)['"]"""
)
TOPIC_IMAGE_RE = re.compile(r"""topicImage\s*\(\s*(\d+)\s*,""")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 "
    "CET-LinkChecker/1.0"
)
REQUEST_TIMEOUT = 12
CET_REQUEST_TIMEOUT = (8, 25)  # (連線, 讀取) 秒；官網連線較慢時仍給足夠時間
MAX_WORKERS = 2  # 外部網址；官網改為逐筆檢查並穿插暫停
THROTTLE_EVERY = 10  # 每檢查幾筆官網連結後暫停一次
THROTTLE_SLEEP_MIN = 1.0
THROTTLE_SLEEP_MAX = 4.0
DEFAULT_SITE_BASE = "https://dev.cet-taiwan.org"
WWW_SITE_BASE = "https://www.cet-taiwan.org"
# dev / www 目前使用 HTTP Basic；瀏覽器已記住帳密，檢查程式需自行帶上。
CET_BASIC_AUTH = ("guest", "cet")
CET_AUTH_DOMAIN = "cet-taiwan.org"
ALLOWED_SUFFIXES = {".html", ".htm", ".css", ".js", ".mjs"}
JS_ASSET_EXTS = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".mjs",
    ".json",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".avif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".pdf",
    ".mp4",
    ".webm",
    ".mp3",
    ".php",
}
SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".cursor",
    ".vscode",
    "venv",
    ".venv",
}


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


def select_folder() -> Path:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    repo_root = Path(__file__).resolve().parent.parent
    folder = filedialog.askdirectory(
        title="選擇要檢查的資料夾（將檢查其中所有 HTML / CSS / JS）",
        initialdir=str(repo_root) if repo_root.is_dir() else None,
    )
    root.destroy()
    return Path(folder) if folder else Path()


SKIP_NAME_SUFFIXES = ("_merge.html", "_scoped.css")


def should_skip_file(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in SKIP_NAME_SUFFIXES)


def collect_checkable_files(folder: Path) -> list[Path]:
    files: list[Path] = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if should_skip_file(path):
            continue
        if path.suffix.lower() in ALLOWED_SUFFIXES:
            files.append(path)
    files.sort(key=lambda p: str(p).lower())
    return files


def rel_display(path: Path, folder: Path) -> str:
    try:
        return str(path.resolve().relative_to(folder.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def build_session() -> requests.Session:
    session = requests.Session()
    retry_kwargs = {
        "total": 2,
        "connect": 2,
        "read": 1,
        "backoff_factor": 0.4,
        "status_forcelist": (502, 503, 504),
        "raise_on_status": False,
    }
    try:
        retry = Retry(allowed_methods=frozenset({"GET", "HEAD"}), **retry_kwargs)
    except TypeError:
        retry = Retry(method_whitelist=frozenset({"GET", "HEAD"}), **retry_kwargs)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def is_cet_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == CET_AUTH_DOMAIN or host.endswith("." + CET_AUTH_DOMAIN)


def is_root_relative(url: str) -> bool:
    """以 / 開頭、但不是 //host 的相對網址。"""
    u = url.strip()
    return u.startswith("/") and not u.startswith("//")


def normalize_site_base(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url:
        return DEFAULT_SITE_BASE
    if url.startswith("//"):
        url = "https:" + url
    elif "://" not in url:
        url = "https://" + url
    return url.rstrip("/")


def ask_site_base_url() -> str:
    print("\n檔案內有以 / 開頭的相對網址（例如 /sites/.../a.webp）。")
    print("請選擇用來檢查的網站根網址：")
    print(f"  [1] {DEFAULT_SITE_BASE}  （預設，直接 Enter）")
    print(f"  [2] {WWW_SITE_BASE}")
    print("  [3] 自行輸入")
    choice = input("> ").strip()
    if choice in {"", "1"}:
        return DEFAULT_SITE_BASE
    if choice == "2":
        return WWW_SITE_BASE
    if choice == "3":
        custom = input("請輸入網址：").strip()
        if not custom:
            print(f"未輸入，改用預設：{DEFAULT_SITE_BASE}")
            return DEFAULT_SITE_BASE
        return normalize_site_base(custom)
    if choice.startswith(("http://", "https://", "//")):
        return normalize_site_base(choice)
    print(f"無法辨識，改用預設：{DEFAULT_SITE_BASE}")
    return DEFAULT_SITE_BASE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CET Taiwan HTML / CSS / JS 連結檢查")
    parser.add_argument(
        "--base-url",
        default=None,
        help="相對路徑（/sites/...）要接上的網站根網址",
    )
    return parser.parse_args()


def should_skip_url(url: str) -> bool:
    u = url.strip()
    if not u or u.startswith("#"):
        return True
    lower = u.lower()
    if lower.startswith(
        ("data:", "javascript:", "mailto:", "tel:", "sms:", "whatsapp:", "about:")
    ):
        return True
    # 僅 query 或僅 hash（例如 ?id=1），沒有實際路徑可檢查
    path_only = u.split("?", 1)[0].split("#", 1)[0].strip()
    return not path_only


def link_rel_values(tag) -> set[str]:
    rel = tag.get("rel")
    if not rel:
        return set()
    if isinstance(rel, list):
        parts = rel
    else:
        parts = str(rel).split()
    return {str(p).lower() for p in parts if p}


def is_origin_only_url(url: str) -> bool:
    parsed = urlparse(url)
    path = (parsed.path or "").strip()
    return path in {"", "/"} and not parsed.query


def looks_like_url(value: str) -> bool:
    """meta content 等屬性可能是文字或網址，只收看起來像路徑／網址的值。"""
    u = value.strip()
    if not u:
        return False
    lower = u.lower()
    return lower.startswith(("http://", "https://", "//", "/", "../", "./"))


def unescape_js_string(value: str) -> str:
    return value.replace(r"\/", "/").replace(r"\'", "'").replace(r"\"", '"')


def is_js_url_candidate(value: str) -> bool:
    """過濾 class 名、狀態字串，只保留看起來像網址或檔案路徑的 JS 字串。"""
    u = unescape_js_string(value).strip()
    if should_skip_url(u) or "${" in u:
        return False
    lower = u.lower()
    if lower.startswith(("http://", "https://")):
        return bool(urlparse(u).netloc)
    if u.startswith("//") and len(u) > 3:
        return bool(urlparse("https:" + u).netloc)
    if u.startswith("./") or u.startswith("../"):
        path = u.split("?", 1)[0].split("#", 1)[0]
        suffix = Path(unquote(path)).suffix.lower()
        return suffix in JS_ASSET_EXTS or path.count("/") >= 1
    if is_root_relative(u) and u != "/":
        return True
    path = u.split("?", 1)[0].split("#", 1)[0]
    suffix = Path(unquote(path)).suffix.lower()
    if suffix not in JS_ASSET_EXTS or " " in path:
        return False
    name = Path(unquote(path)).name
    return bool(re.match(r"^[A-Za-z0-9_]", name))


def iter_js_urls(text: str) -> list[tuple[str, int]]:
    """從 JS 原文擷取（網址, 字元位移）。"""
    found: list[tuple[str, int]] = []
    seen: set[str] = set()

    def add(raw: str, pos: int) -> None:
        raw = unescape_js_string(raw).strip().rstrip(".,;:)")
        if not is_js_url_candidate(raw) or raw in seen:
            return
        seen.add(raw)
        found.append((raw, pos))

    for m in JS_STRING_RE.finditer(text):
        add(m.group(2), m.start())
    for m in JS_TEMPLATE_RE.finditer(text):
        add(m.group(1), m.start())
    for m in JS_HTTP_RE.finditer(text):
        add(m.group(0), m.start())
    return found


def image_base_to_root_path(image_base: str) -> str:
    """IMAGE_BASE 只保留路徑，檢查時再接上 bat 選擇的網站根網址。"""
    raw = image_base.strip()
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} or raw.startswith("//"):
        path = parsed.path or "/"
    else:
        path = raw
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    return path


def collect_image_base_urls(text: str) -> list[tuple[str, int]]:
    """
    不單獨檢查 IMAGE_BASE 目錄。
    還原 IMAGE_BASE + slug + 副檔名，路徑以 /sites/... 形式留下，供 --base-url 接上。
    """
    assign = IMAGE_BASE_ASSIGN_RE.search(text)
    if not assign:
        return []

    base = image_base_to_root_path(assign.group(1))
    pos = assign.start()
    concats = list(IMAGE_BASE_CONCAT_RE.finditer(text))
    if not concats:
        return []

    image_slugs = [
        m.group(1) for m in re.finditer(r"""imageSlug\s*:\s*['"]([^'"]+)['"]""", text)
    ]
    named_slugs = [
        m.group(1) for m in re.finditer(r"""\bslug\s*:\s*['"]([^'"]+)['"]""", text)
    ]
    topic_ids = [m.group(1) for m in TOPIC_IMAGE_RE.finditer(text)]
    prefix_by_var = {
        m.group(1): m.group(2)
        for m in re.finditer(
            r"""(?:var|let|const)\s+(\w+)\s*=\s*['"]([^'"]+)['"]\s*\+\s*image\.topicId""",
            text,
        )
    }

    found: list[tuple[str, int]] = []
    seen: set[str] = set()

    def add_urls(slugs: list[str], suffix: str) -> None:
        for slug in slugs:
            raw = base + slug + suffix
            if raw in seen:
                continue
            seen.add(raw)
            found.append((raw, pos))

    for m in concats:
        expr = m.group(1).strip()
        suffix = m.group(2)
        var = expr.split(".")[-1].strip()
        if "imageSlug" in expr:
            add_urls(image_slugs, suffix)
        elif var == "slug":
            add_urls(named_slugs, suffix)
        elif var in prefix_by_var:
            add_urls([prefix_by_var[var] + tid for tid in topic_ids], suffix)
        elif image_slugs:
            add_urls(image_slugs, suffix)
        elif named_slugs:
            add_urls(named_slugs, suffix)

    return found


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
        seen.add(raw)
        found.append(
            FoundLink(
                file=path,
                raw=raw,
                line=find_line_number(text, raw),
                context=context,
            )
        )

    for tag in soup.find_all(True):
        tag_name = tag.name or "?"
        skip_hint_href = tag_name == "link" and bool(
            link_rel_values(tag) & CONNECTION_HINT_RELS
        )
        for attr in URL_ATTRS:
            if skip_hint_href and attr == "href":
                continue
            val = tag.get(attr)
            if isinstance(val, str):
                add(val, f"<{tag_name} {attr}>")
        xhref = tag.get("xlink:href")
        if isinstance(xhref, str):
            add(xhref, f"<{tag_name} xlink:href>")
        for attr in SRCSET_ATTRS:
            val = tag.get(attr)
            if isinstance(val, str):
                for u in parse_srcset(val):
                    add(u, f"<{tag_name} {attr}>")
        if tag_name == "meta":
            content = tag.get("content")
            if isinstance(content, str) and looks_like_url(content):
                add(content, "<meta content>")

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
        for m in CSS_IMPORT_RE.finditer(css):
            add(next(g for g in m.groups() if g is not None), "<style> @import")

    # <script> 內文（src 屬性已由 URL_ATTRS 擷取）
    image_base_assign = IMAGE_BASE_ASSIGN_RE.search(text)
    image_base_skip = (
        image_base_assign.group(1).strip().rstrip("/") if image_base_assign else None
    )
    for script_tag in soup.find_all("script"):
        js = script_tag.string or ""
        if not js.strip():
            js = script_tag.get_text() or ""
        if not js.strip():
            continue
        for raw, _pos in iter_js_urls(js):
            if image_base_skip and raw.rstrip("/") == image_base_skip:
                continue
            add(raw, "<script>")
    # 用整份檔案還原 IMAGE_BASE 圖檔，避免 JS 字串裡的 </picture> 干擾解析
    for raw, _pos in collect_image_base_urls(text):
        add(raw, "<script> IMAGE_BASE")

    return found


def extract_from_css(path: Path) -> list[FoundLink]:
    text = path.read_text(encoding="utf-8", errors="replace")
    found: list[FoundLink] = []
    seen: set[str] = set()

    for m in CSS_URL_RE.finditer(text):
        raw = next(g for g in m.groups() if g is not None).strip()
        if should_skip_url(raw) or raw in seen:
            continue
        seen.add(raw)
        line = text.count("\n", 0, m.start()) + 1
        found.append(FoundLink(file=path, raw=raw, line=line, context="css url()"))

    for m in CSS_IMPORT_RE.finditer(text):
        raw = next(g for g in m.groups() if g is not None).strip()
        if should_skip_url(raw) or raw in seen:
            continue
        seen.add(raw)
        line = text.count("\n", 0, m.start()) + 1
        found.append(FoundLink(file=path, raw=raw, line=line, context="css @import"))

    return found


def extract_from_js(path: Path) -> list[FoundLink]:
    text = path.read_text(encoding="utf-8", errors="replace")
    found: list[FoundLink] = []
    seen: set[str] = set()

    image_base_raw = None
    assign = IMAGE_BASE_ASSIGN_RE.search(text)
    if assign:
        image_base_raw = assign.group(1).strip().rstrip("/")

    for raw, pos in iter_js_urls(text):
        if image_base_raw and raw.rstrip("/") == image_base_raw:
            continue
        if raw in seen:
            continue
        seen.add(raw)
        line = text.count("\n", 0, pos) + 1
        found.append(FoundLink(file=path, raw=raw, line=line, context="js"))

    for raw, pos in collect_image_base_urls(text):
        if raw in seen:
            continue
        seen.add(raw)
        line = text.count("\n", 0, pos) + 1
        found.append(FoundLink(file=path, raw=raw, line=line, context="js IMAGE_BASE"))

    return found


def extract_links(path: Path) -> list[FoundLink]:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return extract_from_html(path)
    if suffix == ".css":
        return extract_from_css(path)
    if suffix in {".js", ".mjs"}:
        return extract_from_js(path)
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

    # 協定相對 //cdn.example.com/a.webp
    if raw.startswith("//"):
        return "remote", "https:" + raw

    # 根路徑 /foo/bar.webp → 接上使用者選擇的 base 網址
    if is_root_relative(raw):
        if site_base:
            return "remote", site_base + raw
        return "skip", None

    # 相對路徑
    local = (link.file.parent / unquote(raw.split("?", 1)[0].split("#", 1)[0])).resolve()
    return "local", local


def check_remote(url: str, session: requests.Session) -> tuple[str, str, int | None]:
    """
    一律用 GET（stream）檢查。
    cet-taiwan.org 等主機對不存在的資源 HEAD 仍可能回 200 + Content-Length: 0，
    只有 GET 才會得到真實 404。
    該站需 HTTP Basic（guest / cet），且憑證可能過期，故略過 SSL 驗證。
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    kwargs: dict = {
        "allow_redirects": True,
        "timeout": CET_REQUEST_TIMEOUT if is_cet_host(url) else REQUEST_TIMEOUT,
        "headers": headers,
        "stream": True,
    }
    if is_cet_host(url):
        kwargs["auth"] = HTTPBasicAuth(*CET_BASIC_AUTH)
        kwargs["verify"] = False
    try:
        resp = session.get(url, **kwargs)
        code = resp.status_code
        # 讀一點 body 確保連線完成狀態，再關掉避免下載整張圖
        try:
            next(resp.iter_content(chunk_size=64), None)
        finally:
            resp.close()

        if code == 404:
            # preconnect 類根網址（例如 https://fonts.gstatic.com）常回 404，主機其實活著
            if is_origin_only_url(url):
                return "ok", f"HTTP {code}（主機可連，根路徑無文件）", code
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
        if is_root_relative(link.raw) and not site_base:
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
    if target != link.raw:
        detail = f"{detail}（{target}）"
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


def print_report(report: Report, folder: Path) -> None:
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
            loc = rel_display(r.link.file, folder)
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
            loc = rel_display(r.link.file, folder)
            if r.link.line:
                loc += f":{r.link.line}"
            print(f"\n  {loc}")
            print(f"    連結：{r.link.raw}")
            print(f"    說明：{r.detail}")

    if skipped:
        print("\n--- 已略過 ---")
        for r in skipped:
            loc = rel_display(r.link.file, folder)
            print(f"  · {loc} → {r.link.raw}（{r.detail}）")

    failed = len(broken) + len(errors)
    print("\n" + "=" * 60)
    print(f"共有 {failed} 則連結失敗，{ok} 則成功")
    print("=" * 60)
    if failed == 0:
        print("全部可檢查的連結皆正常。")


def main() -> None:
    args = parse_args()
    print("CET Taiwan - HTML / CSS / JS 連結檢查工具")
    print("-" * 40)
    print("請在跳出的視窗中選擇要檢查的資料夾。")

    folder = select_folder()
    if not folder:
        print("已取消選擇資料夾。")
        sys.exit(0)

    files = collect_checkable_files(folder)
    if not files:
        print(f"資料夾內沒有 HTML / CSS / JS 檔案：{folder}")
        sys.exit(0)

    print(f"\n資料夾：{folder}")
    print(f"找到 {len(files)} 個 HTML / CSS / JS 檔案：")
    for f in files:
        print(f"  · {rel_display(f, folder)}")

    all_links: list[FoundLink] = []
    for f in files:
        try:
            links = extract_links(f)
        except OSError as exc:
            print(f"⚠ 無法讀取 {rel_display(f, folder)}：{exc}", file=sys.stderr)
            continue
        print(f"  {rel_display(f, folder)}：找到 {len(links)} 個連結")
        all_links.extend(links)

    all_links = unique_links(all_links)
    if not all_links:
        print("\n未找到任何連結。")
        sys.exit(0)

    need_base = any(is_root_relative(lnk.raw) for lnk in all_links)
    if args.base_url is not None:
        site_base = normalize_site_base(args.base_url)
    elif need_base:
        site_base = ask_site_base_url()
    else:
        site_base = ""

    if site_base and need_base:
        print(f"\n相對路徑將以 {site_base} 檢查")
    elif need_base and not site_base:
        print("\n未提供 base 網址，以 / 開頭的相對路徑將略過")

    print("cet-taiwan.org 遠端檢查：使用 guest 帳號、IPv4，並略過過期憑證驗證。")
    print(
        f"官網連結改為逐筆檢查，每 {THROTTLE_EVERY} 筆暫停 "
        f"{THROTTLE_SLEEP_MIN:.1f}–{THROTTLE_SLEEP_MAX:.1f} 秒（隨機），降低被封鎖的機會。"
    )

    print(f"\n開始檢查 {len(all_links)} 個連結…")
    session = build_session()
    report = Report()

    # 本機路徑可同步；官網遠端逐筆＋暫停；其他遠端少量並行
    local_jobs: list[FoundLink] = []
    cet_jobs: list[FoundLink] = []
    other_remote_jobs: list[FoundLink] = []
    for link in all_links:
        kind, target = resolve_target(link, site_base)
        if kind != "remote":
            local_jobs.append(link)
        elif isinstance(target, str) and is_cet_host(target):
            cet_jobs.append(link)
        else:
            other_remote_jobs.append(link)

    for link in local_jobs:
        report.results.append(check_link(link, site_base, session))

    if cet_jobs:
        print(f"\n檢查官網連結（{len(cet_jobs)}）…")
        for done, link in enumerate(cet_jobs, start=1):
            report.results.append(check_link(link, site_base, session))
            if done % 5 == 0 or done == len(cet_jobs):
                print(f"  官網進度：{done}/{len(cet_jobs)}")
            if done < len(cet_jobs) and done % THROTTLE_EVERY == 0:
                secs = random.uniform(THROTTLE_SLEEP_MIN, THROTTLE_SLEEP_MAX)
                print(f"  暫停 {secs:.1f} 秒…")
                time.sleep(secs)

    if other_remote_jobs:
        print(f"\n檢查外部連結（{len(other_remote_jobs)}）…")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(check_link, link, site_base, session): link
                for link in other_remote_jobs
            }
            done = 0
            for fut in as_completed(futures):
                report.results.append(fut.result())
                done += 1
                if done % 5 == 0 or done == len(other_remote_jobs):
                    print(f"  外部進度：{done}/{len(other_remote_jobs)}")

    # 依檔名、行號排序，方便閱讀
    report.results.sort(
        key=lambda r: (
            str(r.link.file).lower(),
            r.link.line or 0,
            r.link.raw,
        )
    )
    print_report(report, folder)

    if report.broken or any(r.status == "error" for r in report.results):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已中斷。")
        sys.exit(130)
