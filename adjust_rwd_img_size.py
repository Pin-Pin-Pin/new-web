#!/usr/bin/env python3
"""Download images from HTML, calculate RWD widths, and resize for mb/tbl/dt."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from PIL import Image

Breakpoint = Literal["mb", "tbl", "dt"]

VIEWPORTS: dict[Breakpoint, int] = {"mb": 375, "tbl": 768, "dt": 1400}
SECTION_PADDING: dict[Breakpoint, int] = {"mb": 24, "tbl": 40, "dt": 120}
CONTAINER_MAX_WIDTH: dict[Breakpoint, int] = {"mb": 342, "tbl": 760, "dt": 960}
DEVICE_SUFFIXES: dict[Breakpoint, str] = {"mb": "mb", "tbl": "tbl", "dt": "dt"}

RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}

MEDIA_MIN_WIDTH_RE = re.compile(
    r"@media\s*\(\s*min-width\s*:\s*(\d+)px\s*\)",
    re.IGNORECASE,
)
CLASS_SELECTOR_RE = re.compile(r"\.([a-zA-Z0-9_-]+)")


@dataclass
class CssRule:
    selector: str
    min_width: int
    width: str | None = None
    max_width: str | None = None
    grid_columns: int | None = None


@dataclass
class WidthResult:
    mb: int
    tbl: int
    dt: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImageRecord:
    url: str
    local_name: str
    widths: WidthResult


def parse_css_rules(css_text: str) -> list[CssRule]:
    """Extract class-based width/max-width rules grouped by media query."""
    css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
    rules: list[CssRule] = []
    media_spans: list[tuple[int, int, int, str]] = []
    search_from = 0

    while True:
        media_match = MEDIA_MIN_WIDTH_RE.search(css_text, search_from)
        if not media_match:
            break
        min_width = int(media_match.group(1))
        brace_start = css_text.find("{", media_match.end())
        if brace_start == -1:
            break
        depth = 0
        end_idx = brace_start
        for i in range(brace_start, len(css_text)):
            if css_text[i] == "{":
                depth += 1
            elif css_text[i] == "}":
                depth -= 1
                if depth == 0:
                    end_idx = i
                    content = css_text[brace_start + 1 : end_idx]
                    media_spans.append((media_match.start(), end_idx + 1, min_width, content))
                    search_from = end_idx + 1
                    break
        else:
            break

    default_css = css_text
    for start, end, _, _ in sorted(media_spans, key=lambda s: s[0], reverse=True):
        default_css = default_css[:start] + default_css[end:]

    rules.extend(_parse_rule_chunk(default_css, min_width=0))
    for _, _, min_width, content in media_spans:
        rules.extend(_parse_rule_chunk(content, min_width=min_width))
    return rules


def _parse_rule_chunk(chunk: str, min_width: int) -> list[CssRule]:
    rules: list[CssRule] = []
    depth = 0
    selector_start = 0
    body_start = 0
    i = 0
    while i < len(chunk):
        ch = chunk[i]
        if ch == "{":
            if depth == 0:
                selector = chunk[selector_start:i].strip()
                body_start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                body = chunk[body_start:i]
                rules.extend(_rule_from_block(selector, body, min_width))
                selector_start = i + 1
        i += 1
    return rules


def _rule_from_block(selector: str, body: str, min_width: int) -> list[CssRule]:
    if not CLASS_SELECTOR_RE.search(selector):
        return []
    width_match = re.search(
        r"(?:^|[;\s])width\s*:\s*([^;]+)", body, re.IGNORECASE
    )
    max_width_match = re.search(
        r"(?:^|[;\s])max-width\s*:\s*([^;]+)", body, re.IGNORECASE
    )
    if not width_match and not max_width_match:
        grid_match = re.search(
            r"(?:^|[;\s])grid-template-columns\s*:\s*([^;]+)", body, re.IGNORECASE
        )
        if not grid_match:
            return []
        cols = _count_grid_columns(grid_match.group(1))
        if cols <= 1:
            return []
        return [
            CssRule(
                selector=selector,
                min_width=min_width,
                grid_columns=cols,
            )
        ]
    return [
        CssRule(
            selector=selector,
            min_width=min_width,
            width=width_match.group(1).strip() if width_match else None,
            max_width=max_width_match.group(1).strip() if max_width_match else None,
        )
    ]


def _count_grid_columns(value: str) -> int:
    parts = [p.strip() for p in re.split(r"\s+", value.strip()) if p.strip()]
    return len(parts) if parts else 1


def grid_columns_for(tag: Tag, rules: list[CssRule], bp: Breakpoint) -> int | None:
    for rule in applicable_css_rules(rules, tag, bp):
        if rule.grid_columns and rule.grid_columns > 1:
            return rule.grid_columns
    return None


def load_css_rules(html_path: Path, soup: BeautifulSoup) -> list[CssRule]:
    rules: list[CssRule] = []
    for link in soup.find_all("link", rel=True):
        rel = link.get("rel")
        if not rel or "stylesheet" not in [r.lower() for r in rel]:
            continue
        href = link.get("href")
        if not href or href.startswith("http"):
            continue
        css_path = (html_path.parent / href).resolve()
        if css_path.is_file():
            rules.extend(parse_css_rules(css_path.read_text(encoding="utf-8")))
    return rules


def parse_length(value: str, base: float) -> float | None:
    value = value.strip().lower()
    if value.endswith("px"):
        try:
            return float(value[:-2])
        except ValueError:
            return None
    if value.endswith("%"):
        try:
            return base * float(value[:-1]) / 100.0
        except ValueError:
            return None
    return None


def breakpoint_min_width(bp: Breakpoint) -> int:
    return {"mb": 0, "tbl": 768, "dt": 1200}[bp]


def selector_matches(tag: Tag, selector: str) -> bool:
    """Match simple or descendant class selectors."""
    parts = [p.strip() for p in selector.split(",")]
    classes = get_classes(tag)
    for part in parts:
        if not part:
            continue
        if re.search(r":(?:not|has|nth-|first|last|where|is)\b", part):
            continue
        if re.search(r"[\s>+~]", part):
            tokens = [t.strip() for t in re.split(r"[\s>+~]+", part) if t.strip()]
            if not tokens:
                continue
            target_classes = set(CLASS_SELECTOR_RE.findall(tokens[-1]))
            if not (target_classes & classes):
                continue
            ancestor = tag.parent
            for token in reversed(tokens[:-1]):
                anc_classes = set(CLASS_SELECTOR_RE.findall(token))
                found = False
                while ancestor and isinstance(ancestor, Tag):
                    if anc_classes <= get_classes(ancestor):
                        found = True
                        break
                    ancestor = ancestor.parent
                if not found:
                    break
            else:
                return True
        else:
            rule_classes = set(CLASS_SELECTOR_RE.findall(part))
            if rule_classes & classes:
                return True
    return False


def applicable_css_rules(
    rules: list[CssRule], tag: Tag, bp: Breakpoint
) -> list[CssRule]:
    bp_min = breakpoint_min_width(bp)
    matched: list[CssRule] = []
    for rule in rules:
        if rule.min_width > bp_min:
            continue
        if selector_matches(tag, rule.selector):
            matched.append(rule)
    return sorted(matched, key=lambda r: r.min_width, reverse=True)


def get_classes(tag: Tag) -> set[str]:
    raw = tag.get("class") or []
    return set(raw) if isinstance(raw, list) else {raw}


def col_ratio(classes: set[str], bp: Breakpoint) -> float | None:
    bp_min = breakpoint_min_width(bp)
    ratio = 1.0
    found = False
    for cls in classes:
        col_match = re.fullmatch(r"col(?:-(xs|sm|md|lg|xl|xxl))?-(\d+)", cls)
        if col_match:
            found = True
            prefix, span = col_match.groups()
            prefix_min = {
                None: 0,
                "xs": 0,
                "sm": 576,
                "md": 768,
                "lg": 992,
                "xl": 1200,
                "xxl": 1400,
            }[prefix]
            if prefix_min <= bp_min:
                ratio *= int(span) / 12.0
        elif cls == "col":
            found = True
    return ratio if found else None


def inline_width(tag: Tag, base: float) -> float | None:
    style = tag.get("style") or ""
    width_match = re.search(r"width\s*:\s*([^;]+)", style, re.IGNORECASE)
    if width_match:
        return parse_length(width_match.group(1), base)
    max_width_match = re.search(r"max-width\s*:\s*([^;]+)", style, re.IGNORECASE)
    if max_width_match:
        parsed = parse_length(max_width_match.group(1), base)
        if parsed is not None:
            return min(parsed, base)
    return None


def css_width_for_element(
    tag: Tag, rules: list[CssRule], bp: Breakpoint, base: float
) -> tuple[float | None, float | None, bool]:
    """Return (width, max_width_cap, width_is_absolute_px)."""
    width_value: float | None = None
    max_cap: float | None = None
    width_is_absolute = False

    inline = inline_width(tag, base)
    if inline is not None:
        width_value = inline
        style = tag.get("style") or ""
        width_is_absolute = bool(
            re.search(r"width\s*:\s*[\d.]+px", style, re.IGNORECASE)
        )

    for rule in applicable_css_rules(rules, tag, bp):
        if rule.width:
            parsed = parse_length(rule.width, base)
            if parsed is not None:
                width_value = parsed
                width_is_absolute = rule.width.strip().lower().endswith("px")
                break
    for rule in applicable_css_rules(rules, tag, bp):
        if rule.max_width:
            parsed = parse_length(rule.max_width, base)
            if parsed is not None:
                max_cap = parsed
                break

    return width_value, max_cap, width_is_absolute


def has_container_ancestor(tag: Tag) -> bool:
    for parent in tag.parents:
        if not isinstance(parent, Tag):
            continue
        classes = get_classes(parent)
        if "container-fluid" in classes:
            return False
        if "container" in classes:
            return True
    return False


def base_content_width(bp: Breakpoint, tag: Tag) -> float:
    viewport = VIEWPORTS[bp]
    available = viewport - 2 * SECTION_PADDING[bp]
    if has_container_ancestor(tag):
        return float(min(available, CONTAINER_MAX_WIDTH[bp]))
    return float(available)


def calculate_width_for_img(
    img: Tag, rules: list[CssRule], bp: Breakpoint
) -> tuple[int, list[str]]:
    warnings: list[str] = []
    base = base_content_width(bp, img)
    current = base
    fixed_width: float | None = None

    chain: list[Tag] = []
    for node in img.parents:
        if isinstance(node, Tag) and node.name not in ("html", "body", "[document]"):
            chain.append(node)
    chain.reverse()

    for node in chain:
        parent = node.parent
        if isinstance(parent, Tag):
            cols = grid_columns_for(parent, rules, bp)
            if cols:
                current /= cols

        classes = get_classes(node)
        col = col_ratio(classes, bp)
        if col is not None:
            current *= col

        node_width, max_cap, is_abs = css_width_for_element(node, rules, bp, current)
        if node_width is not None:
            if is_abs:
                fixed_width = node_width
            else:
                current = node_width
        if max_cap is not None:
            current = min(current, max_cap)

    img_classes = get_classes(img)
    if "w-100" not in img_classes:
        img_width, img_max, img_is_abs = css_width_for_element(img, rules, bp, current)
        if img_width is not None:
            if img_is_abs:
                fixed_width = img_width
            else:
                current = img_width
        if img_max is not None:
            current = min(current, img_max)

    if fixed_width is not None:
        current = fixed_width
    elif "w-100" in img_classes:
        pass

    width_attr = img.get("width")
    if width_attr and current == base:
        try:
            attr_width = float(str(width_attr).replace("px", ""))
            scale = VIEWPORTS[bp] / VIEWPORTS["dt"]
            current = attr_width * scale
            warnings.append(f"使用 img width 屬性推算: {attr_width}px")
        except ValueError:
            pass

    result = int(round(current))
    if bp == "mb":
        result *= 2
    return max(result, 1), warnings


def calculate_all_widths(img: Tag, rules: list[CssRule]) -> WidthResult:
    all_warnings: list[str] = []
    widths: dict[Breakpoint, int] = {}
    for bp in ("mb", "tbl", "dt"):
        w, warns = calculate_width_for_img(img, rules, bp)
        widths[bp] = w
        all_warnings.extend(warns)
    return WidthResult(
        mb=widths["mb"], tbl=widths["tbl"], dt=widths["dt"], warnings=all_warnings
    )


def merge_width_results(results: list[WidthResult]) -> WidthResult:
    return WidthResult(
        mb=max(r.mb for r in results),
        tbl=max(r.tbl for r in results),
        dt=max(r.dt for r in results),
        warnings=[w for r in results for w in r.warnings],
    )


def resolve_url(src: str, html_path: Path) -> str:
    if src.startswith(("http://", "https://", "//")):
        if src.startswith("//"):
            return "https:" + src
        return src
    return urljoin(html_path.as_uri(), src)


def filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = unquote(Path(path).name)
    return name or "image"


def is_raster(filename: str) -> bool:
    return Path(filename).suffix.lower() in RASTER_EXTENSIONS


def download_image(url: str, dest: Path, session: requests.Session) -> bool:
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except requests.RequestException as exc:
        print(f"  [錯誤] 下載失敗 {url}: {exc}", file=sys.stderr)
        return False


def resize_image(src: Path, dest: Path, target_width: int) -> int:
    with Image.open(src) as img:
        orig_w, orig_h = img.size
        if target_width >= orig_w:
            out_w, out_h = orig_w, orig_h
        else:
            out_w = target_width
            out_h = int(orig_h * target_width / orig_w)
        resized = img.resize((out_w, out_h), Image.Resampling.LANCZOS)
        resized.save(dest)
        return out_w


def find_html_file(name: str, cwd: Path) -> Path:
    candidate = cwd / name
    if candidate.is_file():
        return candidate
    if not name.endswith(".html"):
        candidate = cwd / f"{name}.html"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"找不到 HTML 檔案: {name}")


def process_html(html_path: Path, dry_run: bool = False) -> list[ImageRecord]:
    stem = html_path.stem
    download_dir = html_path.parent / stem
    output_dir = html_path.parent / f"{stem}_change"

    html_text = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html_text, "html.parser")
    css_rules = load_css_rules(html_path, soup)

    imgs = soup.find_all("img")
    if not imgs:
        print("未找到任何 img 標籤。")
        return []

    url_to_imgs: dict[str, list[Tag]] = {}
    for img in imgs:
        src = img.get("src", "").strip()
        if not src or src.startswith("data:"):
            continue
        url = resolve_url(src, html_path)
        url_to_imgs.setdefault(url, []).append(img)

    if not url_to_imgs:
        print("未找到可下載的圖片。")
        return []

    if not dry_run:
        download_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)

    records: list[ImageRecord] = []
    session = requests.Session()
    session.headers.update({"User-Agent": "adjust_rwd_img_size/1.0"})

    for url, img_tags in url_to_imgs.items():
        local_name = filename_from_url(url)
        width_results = [calculate_all_widths(img, css_rules) for img in img_tags]
        merged = merge_width_results(width_results)

        record = ImageRecord(url=url, local_name=local_name, widths=merged)
        records.append(record)

        if not is_raster(local_name):
            print(f"  [略過] 非點陣圖: {local_name}")
            continue

        local_path = download_dir / local_name
        if not dry_run:
            if not local_path.is_file():
                print(f"  下載: {local_name}")
                if not download_image(url, local_path, session):
                    continue
            else:
                print(f"  已存在: {local_name}")

            for bp in ("mb", "tbl", "dt"):
                suffix = DEVICE_SUFFIXES[bp]
                target_w = merged.__dict__[bp]
                stem_name = Path(local_name).stem
                ext = Path(local_name).suffix
                out_name = f"{stem_name}_{suffix}{ext}"
                out_path = output_dir / out_name
                actual_w = resize_image(local_path, out_path, target_w)
                print(f"    → {out_name} ({actual_w}px)")

    return records


def print_summary(records: list[ImageRecord]) -> None:
    if not records:
        return
    print("\n" + "=" * 72)
    print(f"{'檔名':<30} {'mb':>6} {'tbl':>6} {'dt':>6}")
    print("-" * 72)
    for rec in records:
        w = rec.widths
        print(f"{rec.local_name:<30} {w.mb:>6} {w.tbl:>6} {w.dt:>6}")
        if w.warnings:
            for warn in set(w.warnings):
                print(f"  ⚠ {warn}")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="從 HTML 下載圖片並依 RWD 推算寬度產生 mb/tbl/dt 版本"
    )
    parser.add_argument("--html", help="HTML 檔名（不指定則互動輸入）")
    parser.add_argument(
        "--dry-run", action="store_true", help="只推算寬度，不下載不縮圖"
    )
    args = parser.parse_args()

    html_name = args.html or input("請輸入 HTML 檔名: ").strip()
    if not html_name:
        print("未輸入檔名。", file=sys.stderr)
        sys.exit(1)

    cwd = Path.cwd()
    try:
        html_path = find_html_file(html_name, cwd)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    print(f"處理: {html_path.name}")
    if args.dry_run:
        print("（dry-run 模式：不下載、不縮圖）")

    records = process_html(html_path, dry_run=args.dry_run)
    print_summary(records)

    if not args.dry_run and records:
        stem = html_path.stem
        print(f"\n完成。原始圖: {stem}/  縮圖: {stem}_change/")


if __name__ == "__main__":
    main()
