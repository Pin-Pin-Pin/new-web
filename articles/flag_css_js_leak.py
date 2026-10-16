# -*- coding: utf-8 -*-
"""Scan article CSV exports for CSS/JS that would render as visible text."""
import csv
import html as html_lib
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent

FILES = [
    ROOT / "cet_story_export.csv",
    ROOT / "cet_story_export (1).csv",
    ROOT / "cet_journal_content_export.csv",
]

STYLE_ATTR_RE = re.compile(r"""\sstyle\s*=\s*(['"]).*?\1""", re.I | re.S)
SCRIPT_STYLE_TAG_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
HTML_TAG_RE = re.compile(r"<[^>]+>", re.S)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)

# Visible CSS: selector { property:value } not inside a style tag
CSS_RULE_RE = re.compile(
    r"(?:^|[>\s\"'])"
    r"(?:[a-zA-Z][\w-]*|\.[A-Za-z_][\w-]*|#[A-Za-z_][\w-]*)"
    r"(?:\s*,\s*(?:[a-zA-Z][\w-]*|\.[A-Za-z_][\w-]*|#[A-Za-z_][\w-]*))*"
    r"\s*\{[^{}]{0,800}\}",
    re.M,
)

CSS_PROP_LINE_RE = re.compile(
    r"(?:^|[\s;>{])"
    r"(?:font-size|line-height|margin(?:-(?:top|right|bottom|left))?"
    r"|padding(?:-(?:top|right|bottom|left))?"
    r"|max-width|min-width|display|border(?:-radius)?"
    r"|background(?:-color)?|box-shadow|text-align|color"
    r"|cursor|align-items|justify-content|list-style)"
    r"\s*:\s*[^;<>]{1,80};?",
    re.I,
)

JS_PATTERNS = [
    (r"document\.(?:getElementById|querySelector(?:All)?|write)\s*\(", "document DOM API"),
    (r"addEventListener\s*\(", "addEventListener"),
    (r"function\s+[A-Za-z_$][\w$]*\s*\(", "function 宣告"),
    (r"function\s*\([^)]*\)\s*\{", "匿名 function"),
    (r"setTimeout\s*\(", "setTimeout"),
    (r"\.forEach\s*\(", "forEach"),
    (r"new\s+Array\s*\(", "new Array"),
    (r"dataset\.\w+", "dataset"),
    (r"innerHTML\s*=", "innerHTML"),
    (r"g_[A-Za-z]+\s*=", "全域變數 g_*"),
]


def strip_markup(raw: str) -> str:
    text = html_lib.unescape(raw or "")
    text = SCRIPT_STYLE_TAG_RE.sub(" ", text)
    text = STYLE_ATTR_RE.sub(" ", text)
    text = HTML_TAG_RE.sub("\n", text)
    return text


def detect(raw: str) -> tuple[bool, str, str, str]:
    if not raw or not str(raw).strip():
        return False, "", "", ""

    raw = str(raw)
    reasons = []
    snippets = []
    severity = ""

    stripped = strip_markup(raw)
    leading = stripped.lstrip()[:400]

    leading_css = bool(
        re.match(
            r"^(?:p|h[1-6]|div|span|body|a|table|td|ul|ol|li|\.[\w-]+|#[\w-]+)\s*\{",
            leading,
            re.I,
        )
    )

    comments = CSS_COMMENT_RE.findall(stripped)
    if comments:
        reasons.append("CSS註解 /* */")
        snippets.append(comments[0][:80].replace("\n", " "))

    css_rules = CSS_RULE_RE.findall(stripped)
    css_rules = [r.strip() for r in css_rules if ":" in r and re.search(r"[{;]", r)]
    if css_rules:
        if leading_css:
            reasons.append("文首裸露CSS規則")
        else:
            reasons.append("正文裸露CSS規則")
        snippets.append(css_rules[0][:120].replace("\n", " "))

    props = CSS_PROP_LINE_RE.findall(stripped)
    if props and not css_rules:
        if leading_css or re.search(r"font-size\s*:", leading, re.I) or len(props) >= 2:
            reasons.append("裸露CSS屬性（未包在style）")
            snippets.append(props[0][:80].replace("\n", " "))

    js_labels = []
    iframe_only = False
    for pat, label in JS_PATTERNS:
        m = re.search(pat, stripped)
        if not m:
            continue
        js_labels.append(label)
        start = max(0, m.start() - 20)
        snippets.append(stripped[start : m.end() + 40].replace("\n", " ")[:120])

    if js_labels:
        if js_labels == ["setTimeout"] and "iFrameResize" in stripped:
            reasons.append("文中殘留iframe腳本 setTimeout(iFrameResize)")
            iframe_only = True
        else:
            reasons.append("裸露JS（" + "、".join(dict.fromkeys(js_labels)) + "）")

    seen = set()
    uniq = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)

    if not uniq:
        return False, "", "", ""

    has_css = any("CSS" in r for r in uniq)
    has_full_js = any(r.startswith("裸露JS") for r in uniq)
    if leading_css or has_css or has_full_js:
        severity = "高"
    elif iframe_only:
        severity = "中"
    else:
        severity = "高"

    snippet = " | ".join(dict.fromkeys(s.strip() for s in snippets if s.strip()))[:220]
    return True, "；".join(uniq), snippet, severity


def process_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in ("疑似CSS或JS外洩", "風險等級", "問題類型", "問題片段"):
        if col in df.columns:
            df = df.drop(columns=[col])
    flags, types, excerpts, levels = [], [], [], []
    for body in df["內文"]:
        bad, kind, excerpt, level = detect(body)
        flags.append("是" if bad else "否")
        types.append(kind)
        excerpts.append(excerpt)
        levels.append(level)
    insert_at = list(df.columns).index("標題") + 1
    df.insert(insert_at, "疑似CSS或JS外洩", flags)
    df.insert(insert_at + 1, "風險等級", levels)
    df.insert(insert_at + 2, "問題類型", types)
    df.insert(insert_at + 3, "問題片段", excerpts)
    return df


def main():
    csv.field_size_limit(10_000_000)
    summary_rows = []

    for path in FILES:
        df = process_csv(path)
        out_csv = path.with_name(path.stem + "_flagged.csv")
        out_xlsx = path.with_name(path.stem + "_flagged.xlsx")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")

        flagged = df[df["疑似CSS或JS外洩"] == "是"]
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
            flagged_cols = [c for c in df.columns if c != "內文"]
            flagged[flagged_cols].to_excel(writer, sheet_name="疑似問題文章", index=False)
            compact = df.drop(columns=["內文"], errors="ignore")
            compact.to_excel(writer, sheet_name="全部文章標記", index=False)

        print(f"\n=== {path.name} ===")
        print(f"總篇數: {len(df)}")
        print(f"疑似問題: {len(flagged)}")
        for _, row in flagged.iterrows():
            print(
                f"  nid={row['nid']} | {row['標題'][:40]} | {row['問題類型']}"
            )
            summary_rows.append(
                {
                    "來源檔": path.name,
                    "nid": row["nid"],
                    "標題": row["標題"],
                    "疑似CSS或JS外洩": "是",
                    "風險等級": row["風險等級"],
                    "問題類型": row["問題類型"],
                    "問題片段": row["問題片段"],
                    "議題分類": row.get("議題分類", ""),
                }
            )

    summary = pd.DataFrame(summary_rows)
    summary_path = ROOT / "css_js_leak_suspects.xlsx"
    unique = summary.drop_duplicates(subset=["nid"], keep="first").copy()
    unique["_nid_num"] = pd.to_numeric(unique["nid"], errors="coerce")
    unique["_sev"] = unique["風險等級"].map({"高": 0, "中": 1}).fillna(9)
    unique = unique.sort_values(["_sev", "_nid_num"]).drop(columns=["_nid_num", "_sev"])
    with pd.ExcelWriter(summary_path, engine="openpyxl") as writer:
        unique.to_excel(writer, sheet_name="問題文章清單", index=False)
        summary.to_excel(writer, sheet_name="依來源檔列出", index=False)
    print(f"\n彙總: {summary_path} 不重複 {len(unique)} 篇")
    for _, row in unique.iterrows():
        print(f"  [{row['風險等級']}] nid={row['nid']} {row['標題'][:40]} | {row['問題類型']}")
    print("unique", len(unique))


if __name__ == "__main__":
    main()
