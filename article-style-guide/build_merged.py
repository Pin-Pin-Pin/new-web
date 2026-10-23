# -*- coding: utf-8 -*-
"""Merge the three style guides and append patterns found in article bodies."""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "articles"
CACHE = ART / "_body_cache"
OUT = Path(__file__).resolve().parent / "index.html"
BASE = "https://www.cet-taiwan.org"
csv.field_size_limit(20_000_000)


def load_guides() -> dict:
    """Read the three channels from this folder's index.html."""
    text = OUT.read_text(encoding="utf-8")
    start = text.find('id="guide-data">') + len('id="guide-data">')
    end = text.find("</script>", start)
    guides = json.loads(text[start:end])["channels"]
    for guide in guides.values():
        guide["types"] = [item for item in guide["types"] if not item.get("added")]
        guide["findings"] = [
            item for item in (guide.get("findings") or []) if not str(item).startswith("這次另看")
        ]
    return guides


def story_csv() -> dict[str, str]:
    rows = {}
    path = ART / "cet_story_export.csv"
    if not path.exists():
        return rows
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[row["nid"].strip()] = row.get("內文") or ""
    return rows


def fetch(url: str) -> None:
    nid = re.search(r"/(\d+)$", url).group(1)
    path = CACHE / f"{nid}.html"
    if path.exists() and path.stat().st_size > 500:
        return
    response = requests.get(url, headers={"User-Agent": "cet-style-guide/1.0"}, timeout=40)
    response.raise_for_status()
    response.encoding = "utf-8"
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(response.text, encoding="utf-8")


def prefetch(urls: list[str]) -> None:
    missing = []
    for url in urls:
        nid = re.search(r"/(\d+)$", url).group(1)
        path = CACHE / f"{nid}.html"
        if not path.exists() or path.stat().st_size < 500:
            missing.append(url)
    if not missing:
        print("cache ready", len(urls))
        return
    print("fetch", len(missing))
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch, url): url for url in missing}
        done = 0
        for future in as_completed(futures):
            done += 1
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001
                print("fail", futures[future], exc)
            if done % 40 == 0:
                print(" fetched", done, "/", len(missing))


def field_html(url: str, csv_bodies: dict[str, str]) -> str:
    nid = re.search(r"/(\d+)$", url).group(1)
    path = CACHE / f"{nid}.html"
    if path.exists():
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        node = soup.select_one('[class*="block-field-blocknode"][class*="body"] .field__item')
        if node and node.get_text(strip=True):
            return str(node)
    return csv_bodies.get(nid) or ""


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def esc_src(html: str) -> str:
    return (
        html.replace('src="/', f'src="{BASE}/')
        .replace("src='/", f"src='{BASE}/")
        .replace('href="/', f'href="{BASE}/')
        .replace("href='/", f"href='{BASE}/")
    )


def snippet(node, limit: int = 700) -> str:
    if node is None:
        return ""
    html = esc_src(str(node))
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup.select("script, iframe[src*='civicrm'], style"):
        if bad.name == "iframe" and "youtu" not in (bad.get("src") or ""):
            bad.decompose()
        elif bad.name != "iframe":
            bad.decompose()
    root = soup.find()
    if root and root.name in ("ul", "ol"):
        items = root.find_all("li", recursive=False)
        for extra in items[5:]:
            extra.decompose()
    text = str(soup)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def next_content(tag):
    nxt = tag.find_next_sibling()
    while nxt is not None:
        name = getattr(nxt, "name", None)
        if not name:
            nxt = nxt.find_next_sibling()
            continue
        empty_p = name == "p" and not nxt.get_text(strip=True) and not nxt.find("img")
        if empty_p:
            nxt = nxt.find_next_sibling()
            continue
        return nxt
    return None


def next_kind(tag) -> str:
    nxt = next_content(tag)
    if nxt is None:
        return "none"
    if nxt.name in ("ul", "ol"):
        return "list"
    if nxt.name == "table":
        return "table"
    if nxt.name == "p":
        return "lines"
    return "other"


def mark_kind(tag) -> str:
    if tag.name in ("h2", "h3", "h4"):
        return tag.name
    strong = tag.find("strong")
    text = compact(tag.get_text())
    only_strong = bool(strong) and compact(strong.get_text()) == text and text != ""
    leading_br = False
    for child in tag.children:
        if getattr(child, "name", None) == "br":
            leading_br = True
            break
        if compact(str(child)):
            break
    if only_strong and leading_br:
        return "br-strong"
    if only_strong:
        return "p-strong"
    return "p"


def find_label(soup, pattern: str):
    rx = re.compile(pattern)
    for tag in soup.find_all(["h2", "h3", "h4", "p"]):
        text = compact(tag.get_text())
        if not text or len(text) > 24:
            continue
        if rx.fullmatch(text) or (text.startswith("【") and rx.search(text) and len(text) <= 22):
            return tag
    return None


def width_kind(img) -> str:
    width = (img.get("width") or "").strip().lower()
    height = (img.get("height") or "").strip().lower()
    if width in {"100%", "100"} or height in {"100%", "100"}:
        return "pct"
    if re.fullmatch(r"\d{2,5}", width):
        return "px"
    return "missing"


def alt_kind(img) -> str:
    alt = (img.get("alt") or "").strip()
    if not alt:
        return "empty"
    if re.search(r"\.(jpg|jpeg|png|webp|gif)$", alt, re.I):
        return "filename"
    if re.fullmatch(r"[\w.\- ]{1,40}", alt) and re.search(r"\d{3,}", alt):
        return "filename"
    return "text"


def article_row(art: dict) -> dict:
    return {
        "title": art.get("title") or art["url"],
        "url": art["url"],
        "date": art.get("date") or art.get("activity_date") or "",
    }


def add_example(bucket: dict, art: dict, html: str, role: str = "") -> None:
    if not html or len(bucket["examples"]) >= 3:
        return
    bucket["examples"].append(
        {
            "title": art.get("title") or "",
            "url": art["url"],
            "date": art.get("date") or art.get("activity_date") or "",
            "html": html,
            "role": role,
            "exampleNote": "",
        }
    )


def variant(vid: str, name: str, note: str, hint: str, articles: list, examples: list) -> dict:
    rows = []
    seen = set()
    for art in articles:
        url = art["url"]
        if url in seen:
            continue
        seen.add(url)
        rows.append(article_row(art))
    rows.sort(key=lambda row: row["date"], reverse=True)
    return {
        "id": vid,
        "name": name,
        "note": note,
        "promptHint": hint,
        "articles": rows,
        "examples": examples[:3],
    }


def spread_examples(items: list[dict]) -> list[dict]:
    if len(items) <= 3:
        return items
    indexes = [0, len(items) // 2, len(items) - 1]
    picked = []
    seen = set()
    for index in indexes:
        url = items[index]["url"]
        if url not in seen:
            seen.add(url)
            picked.append(items[index])
    return picked


MARK = {
    "p-strong": "粗體【】",
    "br-strong": "粗體【】前面先加 br",
    "p": "獨立段落【】，沒有粗體",
    "h2": "h2",
    "h3": "h3",
    "h4": "h4",
}
FOLLOW = {
    "list": "下面接清單",
    "lines": "下面接段落",
    "table": "下面接表格",
    "other": "後面是其他內容",
    "none": "後面沒有接內容",
}


def label_type(type_id: str, name: str, summary: str, buckets: dict, none_articles: list, none_note: str, none_hint: str) -> dict | None:
    variants = []
    for key, bucket in buckets.items():
        if not bucket["articles"]:
            continue
        mark, follow = key.split("|", 1)
        label = f"{MARK.get(mark, mark)}，{FOLLOW.get(follow, follow)}"
        variants.append(
            variant(
                key.replace("|", "-"),
                label,
                f"小標本身是{MARK.get(mark, mark)}。緊接的內容是{FOLLOW.get(follow, follow)}。",
                f"這個小標請寫成：{label}。不要同一類文章混用 h 標籤、粗體段落和純【】段落。",
                bucket["articles"],
                spread_examples(bucket["examples"]),
            )
        )
    if not variants:
        return None
    variants.append(
        variant(
            "none",
            "沒有這個小標",
            none_note,
            none_hint,
            none_articles,
            [],
        )
    )
    variants.sort(key=lambda item: len(item["articles"]), reverse=True)
    return {
        "id": type_id,
        "name": name,
        "field": "#body",
        "exclusive": True,
        "added": True,
        "summary": summary,
        "official": "官方範本章節用 h2、h3。範本沒有【活動資訊】這種小標元件，所以要在現稿裡選定一種。",
        "officialHtml": "",
        "variants": variants,
    }


def collect(channel: str, articles: list[dict], bodies: dict[str, str]) -> list[dict]:
    groups: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: {"articles": [], "examples": []}))
    image_w = defaultdict(lambda: {"articles": [], "examples": []})
    image_alt = defaultdict(lambda: {"articles": [], "examples": []})
    hr_g = defaultdict(lambda: {"articles": [], "examples": []})
    quote_g = defaultdict(lambda: {"articles": [], "examples": []})
    under_g = defaultdict(lambda: {"articles": [], "examples": []})
    video_g = defaultdict(lambda: {"articles": [], "examples": []})
    prefix_g = defaultdict(lambda: {"articles": [], "examples": []})
    fields_g = defaultdict(lambda: {"articles": [], "examples": []})
    joint_g = defaultdict(lambda: {"articles": [], "examples": []})
    name_g = defaultdict(lambda: {"articles": [], "examples": []})

    for art in articles:
        soup = BeautifulSoup(bodies.get(art["url"]) or "", "html.parser")
        for bad in soup.select("script, style"):
            bad.decompose()

        imgs = soup.find_all("img")
        if not imgs:
            image_w["none"]["articles"].append(art)
            image_alt["none"]["articles"].append(art)
        else:
            kinds = {width_kind(img) for img in imgs}
            if kinds == {"pct"}:
                key = "pct"
            elif kinds == {"px"}:
                key = "px"
            elif kinds == {"missing"}:
                key = "missing"
            else:
                key = "mixed"
            image_w[key]["articles"].append(art)
            add_example(image_w[key], art, snippet(imgs[0], 400), "圖片")
            alts = {alt_kind(img) for img in imgs}
            alt_key = next(iter(alts)) if len(alts) == 1 else "mixed"
            image_alt[alt_key]["articles"].append(art)
            sample = next((img for img in imgs if alt_kind(img) == alt_key), imgs[0])
            add_example(image_alt[alt_key], art, snippet(sample, 400), "alt")

        hr = soup.find("hr")
        if not hr:
            hr_g["none"]["articles"].append(art)
        else:
            nxt = hr.find_next(["p", "h2", "h3", "ul", "ol"])
            follow = nxt.get_text(" ", strip=True)[:32] if nxt else ""
            if re.search(r"聯合聲明|共同聲明|連署|發起", follow):
                key = "joint"
            elif re.search(r"本文|轉載|出處|投書|資料來源|圖片來源", follow):
                key = "credit"
            elif re.search(r"延伸|相關|參考|閱讀秘書", follow):
                key = "more"
            else:
                key = "between"
            hr_g[key]["articles"].append(art)
            prev = hr.find_previous(["p", "h2", "h3"])
            blob = ""
            if prev:
                blob += snippet(prev, 180) + " "
            blob += "<hr>"
            if nxt:
                blob += " " + snippet(nxt, 220)
            add_example(hr_g[key], art, blob, "分隔線")

        quote = soup.find("blockquote")
        if quote:
            quote_g["yes"]["articles"].append(art)
            add_example(quote_g["yes"], art, snippet(quote, 650), "引言")
        else:
            quote_g["none"]["articles"].append(art)

        underlined = [node for node in soup.find_all("u") if node.get_text(strip=True)]
        if not underlined:
            under_g["none"]["articles"].append(art)
        else:
            longest = max(len(node.get_text(strip=True)) for node in underlined)
            key = "long" if longest > 20 else "short"
            under_g[key]["articles"].append(art)
            node = underlined[0]
            parent = node.parent if node.parent and node.parent.name == "p" else node
            add_example(under_g[key], art, snippet(parent, 420), "底線")

        iframe = soup.find("iframe", src=re.compile(r"youtu", re.I))
        link = soup.find("a", href=re.compile(r"youtu", re.I))
        if iframe:
            video_g["iframe"]["articles"].append(art)
            add_example(video_g["iframe"], art, snippet(iframe, 360), "影片")
        elif link:
            video_g["link"]["articles"].append(art)
            add_example(video_g["link"], art, snippet(link, 360), "影片")
        else:
            video_g["none"]["articles"].append(art)

        prefix_node = soup.find(string=re.compile(r"圖說[:：]|圖片來源[:：]|照片來源[:：]|攝影[:：]"))
        if prefix_node and getattr(prefix_node, "parent", None):
            prefix_g["yes"]["articles"].append(art)
            add_example(prefix_g["yes"], art, snippet(prefix_node.parent, 320), "圖說前綴")
        else:
            prefix_g["none"]["articles"].append(art)

        info = find_label(soup, r"【?(活動資訊|講座資訊|活動辦法)】?")
        if info:
            key = f"{mark_kind(info)}|{next_kind(info)}"
            groups["info"][key]["articles"].append(art)
            nxt = next_content(info)
            html = snippet(info, 220)
            if nxt is not None:
                html += snippet(nxt, 420)
            add_example(groups["info"][key], art, html, compact(info.get_text())[:18])
        else:
            groups["info"]["__none__"]["articles"].append(art)

        note = find_label(soup, r"【?[^】]{0,8}注意事項[^】]{0,8}】?")
        if note:
            key = f"{mark_kind(note)}|{next_kind(note)}"
            groups["note"][key]["articles"].append(art)
            nxt = next_content(note)
            html = snippet(note, 220)
            if nxt is not None:
                html += snippet(nxt, 360)
            add_example(groups["note"][key], art, html, compact(note.get_text())[:18])
        else:
            groups["note"]["__none__"]["articles"].append(art)

        field_list = None
        for lst in soup.find_all(["ul", "ol"]):
            items = [li.get_text(" ", strip=True) for li in lst.find_all("li", recursive=False)]
            hits = sum(bool(re.match(r"(時間|日期|地點|地址|對象|費用|報名|形式|名額|講者|主持)", item)) for item in items)
            if hits >= 2:
                field_list = lst
                break
        field_p = None
        if field_list is None:
            for para in soup.find_all("p"):
                text = para.get_text(" ", strip=True)
                if para.find("br") and len(re.findall(r"(時間|日期|地點|地址|形式|報名)[:：]", text)) >= 2:
                    field_p = para
                    break
        if field_list is not None:
            fields_g[field_list.name]["articles"].append(art)
            add_example(fields_g[field_list.name], art, snippet(field_list, 650), "欄位")
        elif field_p is not None:
            fields_g["p-br"]["articles"].append(art)
            add_example(fields_g["p-br"], art, snippet(field_p, 650), "欄位")
        else:
            fields_g["none"]["articles"].append(art)

        joint = soup.find(string=re.compile(r"共同聲明團體|聯合聲明團體|連署團體|發起團體|發起單位"))
        if joint and getattr(joint, "parent", None):
            parent = joint.find_parent(["p", "h2", "h3", "li", "div"]) or joint.parent
            nxt = next_content(parent) if parent else None
            text = parent.get_text(" ", strip=True) if parent else ""
            label_only = bool(re.fullmatch(r"(共同聲明團體|聯合聲明團體|連署團體|發起團體|發起單位)[:：]?", compact(text)))
            if parent and parent.name in ("ul", "ol"):
                key = parent.name
                html = snippet(parent, 520)
            elif nxt is not None and nxt.name in ("ul", "ol"):
                key = nxt.name
                html = snippet(parent, 180) + snippet(nxt, 420)
            elif parent and parent.find("br"):
                key = "p-br"
                html = snippet(parent, 520)
            elif label_only and nxt is not None and nxt.name == "p":
                key = "next-p"
                html = snippet(parent, 180) + snippet(nxt, 420)
            elif re.search(r"[:：]", text) and len(text) > len("共同聲明團體："):
                key = "inline"
                html = snippet(parent, 520)
            else:
                key = "other"
                html = snippet(parent, 420)
            joint_g[key]["articles"].append(art)
            add_example(joint_g[key], art, html, "團體")
        else:
            joint_g["none"]["articles"].append(art)

        sep_hits = {"slash": 0, "pipe": 0, "paren": 0}
        sep_node = None
        for li in soup.find_all("li"):
            text = li.get_text(" ", strip=True)
            if not re.match(r"(講者|主講|主持|與談|講師|引言)", text):
                continue
            if "／" in text:
                sep_hits["slash"] += 1
                sep_node = sep_node or li
            elif "｜" in text or "|" in text:
                sep_hits["pipe"] += 1
                sep_node = sep_node or li
            elif "（" in text:
                sep_hits["paren"] += 1
                sep_node = sep_node or li
        positive = {key: count for key, count in sep_hits.items() if count}
        if not positive:
            name_g["none"]["articles"].append(art)
        elif len(positive) > 1:
            name_g["mixed"]["articles"].append(art)
            add_example(name_g["mixed"], art, snippet(sep_node.parent if sep_node else sep_node, 420), "姓名")
        else:
            key = next(iter(positive))
            name_g[key]["articles"].append(art)
            add_example(name_g[key], art, snippet(sep_node, 280), "姓名")

    types = []

    def simple_type(type_id, name, summary, official, mapping, groups_map, exclusive=True):
        variants = []
        for key, (label, note, hint) in mapping.items():
            bucket = groups_map.get(key)
            if not bucket or not bucket["articles"]:
                continue
            variants.append(variant(key, label, note, hint, bucket["articles"], spread_examples(bucket["examples"])))
        if len([item for item in variants if item["id"] != "none"]) == 0:
            return None
        variants.sort(key=lambda item: (item["id"] == "none", -len(item["articles"])))
        return {
            "id": type_id,
            "name": name,
            "field": "#body",
            "exclusive": exclusive,
            "added": True,
            "summary": summary,
            "official": official,
            "officialHtml": "",
            "variants": variants,
        }

    image_summary = "看前台文章欄裡的 img。width=\"100%\" 或 height=\"100%\" 是原稿寫死的，圖片會被拉變形。沒寫寬高時，前台有時會補上像素，有時不會。上稿規範要填圖片實際寬高。"
    types.append(
        simple_type(
            "image-size",
            "圖片寬高",
            image_summary,
            "上稿規範：依圖片實際寬高填 width、height。第一張以外加 loading=\"lazy\"。",
            {
                "px": ("寬高是像素", "img 寫了實際像素，例如 width=\"1200\" height=\"750\"。", "圖片寬高填該張圖的實際像素，不要寫 100%。"),
                "pct": ("寬或高是 100%", "至少寬或高被寫成 100%，前台容易把直式、橫式圖拉壞。", "不要把圖片寬高寫成 100%。改填實際像素。"),
                "missing": ("沒寫 width / height", "標籤上沒有寬高，版面高度要等圖片下載才知道。", "輸出 img 時加上實際 width 和 height。"),
                "mixed": ("同一篇混用", "一篇裡同時有像素、100% 或沒寫寬高。", "同一篇圖片用同一種寬高寫法，並填實際像素。"),
                "none": ("這篇沒有內文圖", "內文沒有 img。", "沒有圖片就不要留空的圖片段落。"),
            },
            image_w,
        )
    )
    types.append(
        simple_type(
            "image-alt",
            "圖片替代文字",
            "alt 目前多半是空的，或直接用檔名（20260904-001.webp）。讀螢幕器和圖片載入失敗時都看不到說明。",
            "上稿規範：內容圖片要寫 alt。檔名不要拿來當 alt。",
            {
                "text": ("alt 有說明", "alt 是一句話或圖片內容，不是檔名。", "內容圖片的 alt 寫這張圖在說什麼。"),
                "filename": ("alt 是檔名", "alt 用日期檔名或副檔名。", "不要把檔名放進 alt。改寫圖片內容。"),
                "empty": ("alt 是空的", "有 img，但 alt 空白。", "內容圖片不要留空 alt。純裝飾圖才用空 alt，並確認它真的不帶資訊。"),
                "mixed": ("同一篇混用", "有的圖有說明，有的是空的或檔名。", "同一篇內容圖都寫說明文字。"),
                "none": ("這篇沒有內文圖", "沒有 img 可檢查。", "沒有圖片就不必補 alt。"),
            },
            image_alt,
        )
    )

    info = label_type(
        "event-info",
        "活動／講座資訊小標",
        "【活動資訊】和【講座資訊】是同一種欄位小標。現稿有的用粗體段落，有的用沒有粗體的【】段落，少數才用 h2。下面的時間、地點有的接清單，有的接成一個段落。",
        {key: bucket for key, bucket in groups["info"].items() if key != "__none__"},
        groups["info"]["__none__"]["articles"],
        "內文找不到【活動資訊】、【講座資訊】或【活動辦法】。時間地點可能直接寫，或只放在活動欄。",
        "若這類文章需要活動資訊，小標寫法要跟選定的變體一樣；不需要就不要硬加。",
    )
    note = label_type(
        "event-note",
        "注意事項小標",
        "【報名注意事項】【重要注意事項】這類小標，多半是粗體段落，不是 h2、h3。少數小標前面會先放一個 br 來撐距離。",
        {key: bucket for key, bucket in groups["note"].items() if key != "__none__"},
        groups["note"]["__none__"]["articles"],
        "內文沒有「注意事項」小標。",
        "沒有注意事項就不要另做小標。有的話，沿用選定的標籤，不要混用 h2 和【】。",
    )
    if channel == "events":
        types.extend([item for item in (info, note) if item])
    elif channel == "story" and info and len(groups["info"]) > 1:
        info["summary"] = "觀點庫正文很少用【活動資訊】。講座側記偶爾會寫【講座資訊】，寫法跟活動頁同一批問題。"
        types.append(info)

    field_type = simple_type(
        "event-fields",
        "時間地點怎麼排",
        "活動欄已經有日期、時間、地點。內文還是常再寫一次。差在每個欄位是一個 li，還是塞在同一個 p、用 br 換行。",
        "條列用 ul 或 ol。同一欄位裡要換行才用 br，不要用 br 把整組欄位串成一段。",
        {
            "ul": ("無序清單，一項一個欄位", "時間、地點、形式各是一個 li。講者有時再嵌一層 ul。", "時間、地點、形式、講者用 ul，一項一個 li。不要改成同一個 p 加一串 br。"),
            "ol": ("有序清單", "同一組欄位用 ol。", "這組欄位若沒有先後步驟，改用 ul。"),
            "p-br": ("同一個 p，用 br 分行", "時間：、地點：寫在同一個段落，靠 br 換行。", "不要把整組活動欄位串在同一個 p。改成 ul。"),
            "none": ("內文沒有再列時間地點", "沒有成組的時間、地點欄位。活動頁可能只靠活動欄。", "活動頁的日期地點以活動欄為準。內文若要重列，用選定的清單寫法。"),
        },
        fields_g,
    )
    if field_type and channel in {"events", "story"}:
        if channel == "story":
            field_type["name"] = "講座側記的時間地點"
            field_type["summary"] = "大部分觀點庫不重列時間地點。講座側記有一小部分會在內文再寫主題、時間、地點，寫法跟活動頁一樣分裂。"
        types.append(field_type)

    if channel == "events":
        types.append(
            simple_type(
                "speaker-sep",
                "講者姓名和單位",
                "講者、主持、與談人常寫在清單項裡。姓名和單位之間有人用／，有人用｜，也有括號。",
                "範本沒有規定分隔符。同一類文章要固定一種，避免同一份清單混用。",
                {
                    "slash": ("姓名／單位", "用全形斜線分開姓名和單位或職稱。", "講者寫成「姓名／單位或職稱」。"),
                    "pipe": ("姓名｜單位", "用直線｜分開。", "講者寫成「姓名｜單位或職稱」。"),
                    "paren": ("姓名（單位）", "單位放在括號裡。", "講者寫成「姓名（單位或職稱）」。"),
                    "mixed": ("同一篇混用", "一篇裡同時有／、｜或括號。", "同一篇講者只用一種分隔。"),
                    "none": ("沒有這種講者欄", "清單裡沒有講者、主持、與談或講師欄。", "沒有講者就不必硬加。"),
                },
                name_g,
            )
        )

    if channel == "news":
        types.append(
            simple_type(
                "joint-sign",
                "共同聲明團體",
                "聯合聲明稿的團體名單多寫在文末同一個段落：「共同聲明團體：」或「聯合聲明團體：」後面用頓號把名稱串起來，很少用清單。",
                "多筆資料用 ul 或 ol。團體若是名單，清單比頓號長句好讀；若要沿用現稿，就維持同一個段落。",
                {
                    "inline": ("同一個段落，冒號後面串團體名", "「共同聲明團體：」和名稱寫在同一個 p。多家團體通常用頓號分開。", "共同聲明團體寫成一個 p：「共同聲明團體：」後面串名稱。多家時用頓號。"),
                    "next-p": ("標題自己一段，名單在下一段", "小標只有「共同聲明團體：」，名稱寫在下一個 p。", "若選定這一種，標題一段、名單一段，不要併回同一個 p。"),
                    "p-br": ("同一個段落，用 br 換行", "標題和團體名在同一個 p，中間用 br。", "若選定這一種，團體名之間用 br，不要改成頓號長句。"),
                    "ul": ("標題下面接 ul", "團體名各是一個 li。", "共同聲明團體用 ul，一個團體一個 li。"),
                    "ol": ("標題下面接 ol", "團體名用有序清單。", "團體名單沒有順位時改用 ul。"),
                    "other": ("其他寫法", "有聲明團體字樣，但不是頓號段落、br 或清單。", "不要自創新的落款結構。"),
                    "none": ("沒有共同聲明名單", "一般新聞稿沒有這段名單。", "不是聯合聲明就不要加團體名單。"),
                },
                joint_g,
            )
        )

    hr_type = simple_type(
        "rule",
        "分隔線",
        "hr 有的放在文末，隔開出處或共同聲明；也有的直接插在段落中間。活動內文這一批沒有用 hr。",
        "範本不建議用空白段落撐距離。分隔線只放在正文和文末資訊之間，不要拿來當小標。",
        {
            "credit": ("hr 後面是出處或轉載", "線後面是「本文為……投書」這類出處。", "轉載或出處放在文末，前面加一條 hr。"),
            "joint": ("hr 後面是共同聲明團體", "線後面才是團體名單。", "聯合聲明的團體名單放在文末，前面加一條 hr。"),
            "more": ("hr 後面是延伸或參考", "線後面是延伸閱讀、相關報導或參考資料。", "延伸閱讀若要跟正文分開，前面用 hr，標題仍用既定的小標寫法。"),
            "between": ("hr 在段落之間", "線的後面還是正文、單位說明或下一張圖，不是獨立的文末區塊。", "不要在段落中間加 hr。分隔線只放在正文和文末資訊之間。"),
            "none": ("沒有 hr", "內文沒有分隔線。", "沒有文末資訊就不要加 hr。"),
        },
        hr_g,
    )
    quote_type = simple_type(
        "quote",
        "引言",
        "官方範本的引言用 blockquote。現稿只有一部分真的用了，其餘是一般段落。新聞稿這一批若完全沒用，代表目前新聞不靠引言框。",
        "範本：需要從正文區隔出來的說明用 blockquote。不要用斜體或底線代替引言。",
        {
            "yes": ("blockquote 引言", "整段說明放在 blockquote。有的編按也包在裡面。", "需要引言時用 blockquote，裡面仍是一個一個 p。不要在前面再寫「編按」以外的額外字樣；編按本身沿用編按那一項的決定。"),
            "none": ("沒有引言框", "這篇沒有 blockquote。", "一般段落不要改包 blockquote。"),
        },
        quote_g,
    )
    under_type = simple_type(
        "underline",
        "底線強調",
        "有的稿用 u 給人名或整句加底線。範本沒有這個寫法，底線也容易和連結搞混。",
        "不要為了強調去改字色、字級。連結的底線留給真正的 a。",
        {
            "short": ("底線畫在人名或短詞", "u 包住的文字不長，多半是人名或組織。", "若決定保留這種強調，只加在人名或短詞，用 u。"),
            "long": ("底線畫整句", "一整句話放在 u 裡。", "不要把整句加底線。"),
            "none": ("沒有底線", "內文沒有 u。", "強調改用既定的小標或 strong，不要加底線。"),
        },
        under_g,
    )
    video_type = simple_type(
        "video",
        "YouTube",
        "影片有的直接嵌 iframe，有的只放一則連結，連結文字是影片標題而不是網址。",
        "能用連結就不要嵌 iframe。若一定要嵌，用 YouTube 嵌入網址，並寫上寬高。",
        {
            "iframe": ("嵌入 iframe", "內文有 YouTube iframe。", "影片用 YouTube iframe，寫上 width 和 height。"),
            "link": ("只放連結", "沒有 iframe，a 的文字是影片標題。", "影片不要嵌播放器。用 a，連結文字寫影片標題，不要把網址當文字。"),
            "none": ("沒有 YouTube", "內文沒有 YouTube。", "沒有影片就不要留空白嵌入框。"),
        },
        video_g,
    )
    prefix_type = simple_type(
        "caption-prefix",
        "圖說前綴",
        "少數圖說會寫「圖片來源：」「圖說：」「攝影：」。上稿規範是圖說直接寫內容，不要再加「圖說」兩個字。",
        "有圖說用 figure 包 img 和 figcaption。figcaption 不要以「圖說：」開頭。",
        {
            "yes": ("有圖片來源、圖說或攝影前綴", "圖說文字裡帶這些字。", "若選定保留前綴，只使用這一個詞，並放在 figcaption。"),
            "none": ("沒有這類前綴", "圖說沒有寫圖說、圖片來源、照片來源或攝影。", "圖說不要加「圖說：」。來源若要保留，併進選定的前綴寫法。"),
        },
        prefix_g,
    )
    for item in (hr_type, quote_type, under_type, video_type, prefix_type):
        if item:
            types.append(item)

    kept = []
    for item in types:
        if not item:
            continue
        positive = sum(len(row["articles"]) for row in item["variants"] if row["id"] != "none")
        if item["id"] in {"event-info", "event-note"} or positive >= 3:
            kept.append(item)
    return kept


def main() -> None:
    guides = load_guides()
    guides["story"]["findings"] = [
        "標題和副標的 HTML 幾乎每篇都一樣。h1 是標題欄，副標是純文字，沒有人在副標裡用 br、p 或 ul。要決定的是文字放哪裡。",
        "日期不在副標。它在標題旁的時間欄。副標目前主要放作者，但也有人放系列篇名、導語，或整個留空。",
        "多筆補充、參考資料和延伸閱讀沒有統一寫法。同一個角色同時出現 ul、ol、一個 p 裡連續 br，以及每筆各一個 p。",
    ]
    guides["story"]["ui"] = {
        "title": "議題觀點庫上稿樣式對照",
        "lede": "比較議題觀點庫同一種內容的不同寫法。點類型、再點寫法，看實際效果、HTML 和原頁。決定後把 prompt 交給之後上稿的 AI。",
        "storeKey": "cet-story-style-v1",
        "notePlaceholder": "例如：副標統一成「文／單位 姓名」，系列名留在標題。",
        "scopeNote": "列表後面還有更舊的文章，不在這次對照裡。官方範本：node/100000。",
    }
    guides["story"]["promptIntro"] = [
        "你是地球公民基金會議題觀點庫的上稿編輯。之後整理或新寫 story 文章時，請依下列已決定的樣式輸出。",
        "",
        "欄位對應：",
        "- 文章標題寫在 Drupal 標題欄，前台是 h1.title。不要在內文再重複一次標題。",
        "- 副標寫在副標題欄，前台是 .entity-subtitle。這個欄位只放純文字，不要加 br、p、ul。",
        "- 內文寫在 body 欄，前台是 #body。",
        "- 發布日期用系統時間，不要再寫進標題或副標。",
    ]
    guides["story"]["label"] = "議題觀點庫"
    guides["news"]["label"] = "聲明／新聞稿"
    guides["events"]["label"] = "活動"

    indexes = {}
    for key, filename in (
        ("story", "story_style_analysis.json"),
        ("news", "news_style_analysis.json"),
        ("events", "events_style_analysis.json"),
    ):
        indexes[key] = json.loads((ART / filename).read_text(encoding="utf-8"))["articles_index"]

    urls = [art["url"] for rows in indexes.values() for art in rows]
    prefetch(urls)
    csv_bodies = story_csv()
    bodies = {art["url"]: field_html(art["url"], csv_bodies) for rows in indexes.values() for art in rows}

    extra_findings = {
        "story": "這次另看前台內文：圖片寬高與 alt、引言、分隔線、底線、YouTube、圖說前綴。觀點庫幾乎不用【活動資訊】；講座側記才偶爾重列時間地點。",
        "news": "這次另看前台內文：圖片寬高與 alt、文末 hr、共同聲明團體、底線、圖說前綴。這批新聞沒有 blockquote，也沒有【活動資訊】小標。",
        "events": "這次另看【活動資訊】【講座資訊】【注意事項】是粗體、純【】還是 h 標籤，以及時間地點用清單還是 br。活動內文沒有拿 hr 當分隔。",
    }
    for key, guide in guides.items():
        guide["findings"] = list(guide.get("findings") or [])
        guide["findings"].append(extra_findings[key])
        added = collect(key, indexes[key], bodies)
        guide["types"].extend(added)
        print(f"\n[{key}] +{len(added)} types")
        for kind in added:
            print(" ", kind["name"])
            for item in kind["variants"]:
                print(f"    {len(item['articles']):4} {item['id']} {item['name']}")

    payload = json.dumps({"channels": guides}, ensure_ascii=False).replace("<", "\\u003c")
    html = TEMPLATE.replace("__GUIDE_JSON__", payload)
    OUT.write_text(html, encoding="utf-8")
    print("wrote", OUT, "bytes", OUT.stat().st_size)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>上稿樣式對照</title>
  <meta name="description" content="地球公民基金會議題觀點庫、聲明新聞稿、活動文章的上稿樣式對照。用分頁切換三類文章，並比較同一種內容的不同寫法。">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&amp;display=swap" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    :root {
      --cet: #1f7a4d;
      --cet-dark: #145736;
      --ink: #1c2822;
      --muted: #5c6b63;
      --line: #d7e2db;
      --paper: #f6f8f6;
    }
    body {
      font-family: "Noto Sans TC", sans-serif;
      color: var(--ink);
      background: var(--paper);
    }
    img { display: block; max-width: 100%; height: auto; }
    a { color: var(--cet-dark); }
    .skip-link {
      position: absolute;
      left: 1rem;
      top: -3rem;
      background: #fff;
      padding: .5rem 1rem;
      z-index: 10;
    }
    .skip-link:focus { top: .5rem; }
    .site-header {
      background: #fff;
      border-bottom: 1px solid var(--line);
    }
    .eyebrow {
      color: var(--cet);
      font-weight: 700;
      letter-spacing: .04em;
    }
    .channel-tab,
    .type-nav .nav-link,
    .variant-tab {
      min-height: 44px;
      cursor: pointer;
    }
    .channel-tab {
      color: var(--ink);
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: .5rem 1rem;
      font-weight: 700;
    }
    .channel-tab.active {
      background: var(--cet);
      border-color: var(--cet);
      color: #fff;
    }
    .type-nav .nav-link {
      text-align: left;
      color: var(--ink);
      border-radius: .5rem;
    }
    .type-nav .nav-link.active {
      background: var(--cet);
      color: #fff;
    }
    .type-nav .nav-link.active .count-pill {
      background: #fff;
      color: var(--cet-dark);
    }
    .nav-label {
      margin: .75rem .25rem .25rem;
      color: var(--muted);
      font-size: .75rem;
      font-weight: 700;
    }
    .channel-tab:focus-visible,
    .type-nav .nav-link:focus-visible,
    .variant-tab:focus-visible,
    .btn:focus-visible,
    a:focus-visible {
      outline: 3px solid #f0b429;
      outline-offset: 2px;
    }
    .variant-tab { white-space: nowrap; }
    .panel {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: .75rem;
    }
    .article-preview {
      font-size: 1rem;
      line-height: 1.8;
      color: var(--ink);
    }
    .article-preview h1.title {
      font-size: 1.75rem;
      line-height: 1.35;
      font-weight: 700;
      margin: 0 0 .75rem;
    }
    .article-preview .entity-subtitle {
      margin: 0 0 1rem;
      color: #3d4f46;
      font-size: 1rem;
    }
    .article-preview .entity-subtitle.is-empty {
      color: #8a978f;
    }
    .article-preview .node-date {
      margin: 0 0 .5rem;
      color: var(--muted);
      font-size: .875rem;
    }
    .article-preview p { margin: 0 0 1rem; }
    .article-preview h2 {
      font-size: 1.375rem;
      line-height: 1.4;
      font-weight: 700;
      margin: 1.5rem 0 .75rem;
    }
    .article-preview h3 {
      font-size: 1.125rem;
      line-height: 1.45;
      font-weight: 700;
      margin: 1.25rem 0 .5rem;
    }
    .article-preview ul,
    .article-preview ol {
      margin: 0 0 1rem;
      padding-left: 1.25rem;
    }
    .article-preview li { margin: .25rem 0; }
    .article-preview blockquote {
      margin: 0 0 1rem;
      padding: .75rem 1rem;
      border-left: 4px solid var(--cet);
      background: #f3faf6;
    }
    .article-preview img { margin-bottom: .5rem; }
    .article-preview table {
      width: 100%;
      border-collapse: collapse;
      font-size: .9375rem;
      margin-bottom: 1rem;
    }
    .article-preview th,
    .article-preview td {
      border: 1px solid var(--line);
      padding: .5rem .75rem;
      vertical-align: top;
    }
    .article-preview th { background: #e7f5ee; }
    .article-preview hr { margin: 1rem 0; border-color: var(--line); opacity: 1; }
    .source-code {
      white-space: pre-wrap;
      word-break: break-word;
      font-size: .8125rem;
      background: #14211b;
      color: #e7f5ee;
      border-radius: .5rem;
      padding: 1rem;
      max-height: 16rem;
      overflow: auto;
    }
    .count-pill {
      background: #e7f5ee;
      color: var(--cet-dark);
      border-radius: 999px;
      padding: .125rem .5rem;
      font-size: .75rem;
      font-weight: 700;
    }
    .finding {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: .75rem;
      height: 100%;
      padding: 1rem;
    }
    .prompt-box {
      min-height: 16rem;
      font-size: .9375rem;
      line-height: 1.7;
    }
    @media (min-width: 992px) {
      .type-nav { position: sticky; top: 1rem; }
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#compare">跳到樣式比較</a>
  <header class="site-header">
    <div class="container py-4">
      <p class="eyebrow mb-2">地球公民基金會</p>
      <h1 class="h2 mb-3">上稿樣式對照</h1>
      <p class="mb-3">議題觀點庫、聲明／新聞稿、活動文章分頁對照。點類型、再點寫法，看實際效果、HTML 和原頁。標成「新增」的是原本三份對照沒有拆開的面向。決定後，把下面的 prompt 交給之後上稿的 AI。</p>
      <div class="d-flex flex-wrap gap-2" id="channel-nav" role="tablist" aria-label="文章類別"></div>
    </div>
  </header>

  <main class="container py-4">
    <h2 class="h4 mb-2" id="page-title">上稿樣式對照</h2>
    <p class="mb-2" id="page-lede"></p>
    <p class="mb-4 text-secondary" id="scope-line"></p>
    <div class="row g-3 mb-4" id="findings"></div>

    <div class="row g-4" id="compare">
      <div class="col-lg-3">
        <nav class="type-nav panel p-2" aria-label="內容類型">
          <div class="nav flex-row flex-lg-column flex-nowrap overflow-auto" id="type-nav" role="tablist"></div>
        </nav>
      </div>
      <div class="col-lg-9">
        <div class="panel p-3 p-lg-4" id="type-panel"></div>
      </div>
    </div>

    <section class="panel p-3 p-lg-4 mt-4" id="decide">
      <h2 class="h4">選定後的上稿 prompt</h2>
      <p>每一類文章各自記一份選擇。點「採用這個寫法」後，這裡會組成可以貼給 AI 的說明。</p>
      <div id="decision-list" class="mb-3"></div>
      <label class="form-label" for="decision-note">補充決定</label>
      <textarea class="form-control mb-3" id="decision-note" rows="3"></textarea>
      <textarea class="form-control prompt-box mb-3" id="prompt-box" readonly></textarea>
      <div class="d-flex flex-wrap align-items-center gap-2">
        <button type="button" class="btn btn-success" id="copy-prompt">複製 prompt</button>
        <p class="mb-0" id="copy-status" role="status"></p>
      </div>
    </section>
  </main>

  <script type="application/json" id="guide-data">__GUIDE_JSON__</script>
  <script>
    const pack = JSON.parse(document.getElementById("guide-data").textContent);
    const channels = pack.channels;
    const state = {
      channel: "story",
      typeId: "",
      variantId: {},
      exampleIndex: {},
      decisions: {},
      note: ""
    };

    function guide() {
      return channels[state.channel];
    }

    function storeKey() {
      return (guide().ui && guide().ui.storeKey) || ("cet-" + state.channel + "-style-v1");
    }

    function noteKey() {
      return storeKey() + "-note";
    }

    function loadStore() {
      try {
        state.decisions = JSON.parse(localStorage.getItem(storeKey()) || "{}");
        state.note = localStorage.getItem(noteKey()) || "";
      } catch (err) {
        state.decisions = {};
        state.note = "";
      }
    }

    function typeById(id) {
      return guide().types.find((item) => item.id === id) || guide().types[0];
    }

    function variantById(type, id) {
      return type.variants.find((item) => item.id === id) || type.variants[0];
    }

    function save() {
      localStorage.setItem(storeKey(), JSON.stringify(state.decisions));
      localStorage.setItem(noteKey(), state.note);
    }

    function readHash() {
      const raw = decodeURIComponent(location.hash.replace(/^#/, ""));
      if (!raw || raw === "decide") return;
      const parts = raw.split("/");
      if (channels[parts[0]]) {
        state.channel = parts[0];
        parts.shift();
      }
      loadStore();
      const typeId = parts[0];
      const variantId = parts[1];
      if (typeId && guide().types.some((item) => item.id === typeId)) {
        state.typeId = typeId;
        if (variantId && typeById(typeId).variants.some((item) => item.id === variantId)) {
          state.variantId[state.channel + ":" + typeId] = variantId;
        }
      }
    }

    function writeHash() {
      const typeId = state.typeId;
      const variantId = state.variantId[state.channel + ":" + typeId];
      const next = variantId ? `#${state.channel}/${typeId}/${variantId}` : `#${state.channel}/${typeId}`;
      if (location.hash !== next) history.replaceState(null, "", next);
    }

    function currentVariant(type) {
      const chosen = state.variantId[state.channel + ":" + type.id] || state.decisions[type.id];
      return variantById(type, chosen);
    }

    function escapeHtml(text) {
      return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function renderChannels() {
      document.getElementById("channel-nav").innerHTML = Object.entries(channels).map(([id, item]) => {
        const active = id === state.channel ? "active" : "";
        const selected = id === state.channel ? "true" : "false";
        return `<button type="button" class="channel-tab ${active}" role="tab" aria-selected="${selected}" data-channel="${id}">${escapeHtml(item.label)}</button>`;
      }).join("");
    }

    function renderHead() {
      const ui = guide().ui || {};
      document.title = ui.title || "上稿樣式對照";
      document.getElementById("page-title").textContent = ui.title || "";
      document.getElementById("page-lede").textContent = ui.lede || "";
      document.getElementById("decision-note").placeholder = ui.notePlaceholder || "";
      const scopeNote = ui.scopeNote || "";
      document.getElementById("scope-line").textContent =
        `範圍：${guide().source}，共 ${guide().articleCount} 篇（${guide().dateFrom} 到 ${guide().dateTo}）。${scopeNote}`;
      document.getElementById("findings").innerHTML = (guide().findings || []).map((text) =>
        `<div class="col-md-6 col-xl-3"><p class="finding mb-0">${escapeHtml(text)}</p></div>`
      ).join("");
    }

    function renderNav() {
      let seenNew = false;
      document.getElementById("type-nav").innerHTML = guide().types.map((type) => {
        let label = "";
        if (type.added && !seenNew) {
          seenNew = true;
          label = '<p class="nav-label">這次補上的面向</p>';
        }
        const active = type.id === state.typeId ? "active" : "";
        const pressed = type.id === state.typeId ? "true" : "false";
        const mark = state.decisions[type.id] ? '<span class="count-pill">已選</span>' : "";
        const added = type.added ? '<span class="count-pill">新增</span>' : "";
        return `${label}<button type="button" class="nav-link ${active}" role="tab" aria-selected="${pressed}" data-type="${type.id}">${escapeHtml(type.name)} ${added} ${mark}</button>`;
      }).join("");
    }

    function renderPanel() {
      const type = typeById(state.typeId);
      const variant = currentVariant(type);
      state.variantId[state.channel + ":" + type.id] = variant.id;
      const exampleKey = `${state.channel}:${type.id}:${variant.id}`;
      const exampleIndex = state.exampleIndex[exampleKey] || 0;
      const example = variant.examples[exampleIndex] || null;
      const share = guide().articleCount ? Math.round((variant.articles.length / guide().articleCount) * 100) : 0;
      const countLabel = type.exclusive
        ? `${variant.articles.length} / ${guide().articleCount} 篇（${share}%）`
        : `${variant.articles.length} 篇出現過這個寫法`;
      const adopted = state.decisions[type.id] === variant.id;
      const tabs = type.variants.map((item) => {
        const on = item.id === variant.id ? "active" : "";
        const chosen = state.decisions[type.id] === item.id ? " ✓" : "";
        return `<button type="button" class="nav-link variant-tab ${on}" data-variant="${item.id}">${escapeHtml(item.name)}${chosen}<span class="d-block small">${item.articles.length} 篇</span></button>`;
      }).join("");
      const exampleButtons = variant.examples.map((item, index) => {
        const on = index === exampleIndex ? "btn-success" : "btn-outline-success";
        const label = item.role ? `範例 ${index + 1}・${item.role}` : `範例 ${index + 1}`;
        return `<button type="button" class="btn ${on}" data-example="${index}">${escapeHtml(label)}</button>`;
      }).join("");
      const preview = example ? example.html : "<p>這個寫法沒有可預覽的片段。</p>";
      const note = example && example.exampleNote ? `<p class="small text-secondary mb-2">${escapeHtml(example.exampleNote)}</p>` : "";
      const sourceLink = example
        ? `<a class="btn btn-outline-success" href="${escapeHtml(example.url)}" target="_blank" rel="noopener noreferrer">打開原頁看正式站效果</a>`
        : "";
      const code = example ? example.html : "";
      const articles = variant.articles.slice(0, 8).map(articleLink).join("");
      const rest = variant.articles.slice(8);
      const restHtml = rest.length
        ? `<details class="mt-2"><summary>其餘 ${rest.length} 篇</summary><ul class="mt-2 mb-0">${rest.map(articleLink).join("")}</ul></details>`
        : "";
      const official = type.officialHtml
        ? `<div class="mt-3"><p class="fw-bold mb-2">官方範本實際片段</p><div class="article-preview border rounded p-3">${type.officialHtml}</div></div>`
        : "";

      document.getElementById("type-panel").innerHTML = `
        <p class="eyebrow mb-2">${escapeHtml(type.field)}</p>
        <h2 class="h3">${escapeHtml(type.name)}</h2>
        <p>${escapeHtml(type.summary)}</p>
        <p class="mb-3">${escapeHtml(type.official)} <a href="${guide().templateUrl}" target="_blank" rel="noopener noreferrer">打開官方範本</a></p>
        ${official}
        <div class="nav nav-pills flex-nowrap overflow-auto gap-2 py-3" role="tablist" aria-label="寫法">${tabs}</div>
        <p class="mb-2"><span class="count-pill">${countLabel}</span></p>
        <p>${escapeHtml(variant.note)}</p>
        <div class="d-flex flex-wrap gap-2 mb-3" aria-label="這個寫法的範例">${exampleButtons}</div>
        ${note}
        <h3 class="h6">實際效果</h3>
        <div class="article-preview border rounded p-3 mb-3">${preview}</div>
        <div class="d-flex flex-wrap gap-2 mb-4">
          ${sourceLink}
          <button type="button" class="btn ${adopted ? "btn-success" : "btn-dark"}" id="adopt-btn">${adopted ? "已採用這個寫法" : "採用這個寫法"}</button>
          <a class="btn btn-link" href="#decide">到下面產生 prompt</a>
        </div>
        <h3 class="h6">使用這個寫法的文章</h3>
        <ul class="mb-3">${articles || "<li>沒有對應文章</li>"}</ul>
        ${restHtml}
        <h3 class="h6 mt-3">HTML</h3>
        <pre class="source-code mb-0">${escapeHtml(code)}</pre>
      `;
      writeHash();
    }

    function articleLink(article) {
      const date = article.date ? `（${escapeHtml(article.date)}）` : "";
      return `<li class="mb-1"><a href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(article.title)}</a>${date}</li>`;
    }

    function renderDecisions() {
      document.getElementById("decision-list").innerHTML = guide().types.map((type) => {
        const chosen = type.variants.find((item) => item.id === state.decisions[type.id]);
        const label = chosen ? chosen.name : "尚未選擇";
        return `<p class="mb-1"><a href="#${state.channel}/${type.id}/${chosen ? chosen.id : type.variants[0].id}">${escapeHtml(type.name)}</a>：${escapeHtml(label)}</p>`;
      }).join("");
      document.getElementById("decision-note").value = state.note;
      document.getElementById("prompt-box").value = buildPrompt();
    }

    function buildPrompt() {
      const lines = (guide().promptIntro || []).slice();
      lines.push("");
      lines.push(`對照範圍是 ${guide().source}，共 ${guide().articleCount} 篇。${guide().templateUrl ? "官方撰寫範本：" + guide().templateUrl : ""}`);
      lines.push("範本已規定：章節用 h2、h3，條列用 ul 或 ol，項目內換行才用 br（shift+enter），引言用 blockquote，正文一段一個 p。不要改字級、字色、字體，中文不要斜體，不要左右對齊，不要用空白段落撐距離。");
      lines.push("圖片：內容圖用 img，有圖說時用 figure 包 img 和 figcaption，figcaption 不要再加「圖說」二字。width、height 填實際像素；不是第一張圖就加 loading=\"lazy\"。表格表頭用 th，內容用 td。");
      lines.push("");
      lines.push("這次同事選定的寫法如下。若某項寫「尚未決定」，維持範本，不要自創第三種寫法。");
      guide().types.forEach((type) => {
        const chosen = type.variants.find((item) => item.id === state.decisions[type.id]);
        lines.push("");
        lines.push(`## ${type.name}（${type.field}）`);
        if (!chosen) {
          lines.push("尚未決定。");
          lines.push("可選寫法：" + type.variants.map((item) => item.name).join("、"));
          return;
        }
        const sample = chosen.examples[0];
        lines.push(`採用：${chosen.name}`);
        lines.push(chosen.promptHint);
        if (sample) lines.push(`範例原頁：${sample.url}`);
        const rejected = type.variants.filter((item) => item.id !== chosen.id).map((item) => item.name);
        if (rejected.length) lines.push("不要混用：" + rejected.join("、"));
      });
      if (state.note.trim()) {
        lines.push("");
        lines.push("## 補充決定");
        lines.push(state.note.trim());
      }
      return lines.join("\n");
    }

    function renderAll() {
      if (!guide().types.some((item) => item.id === state.typeId)) {
        state.typeId = guide().types[0].id;
      }
      renderChannels();
      renderHead();
      renderNav();
      renderPanel();
      renderDecisions();
    }

    document.getElementById("channel-nav").addEventListener("click", (event) => {
      const button = event.target.closest("[data-channel]");
      if (!button) return;
      state.channel = button.dataset.channel;
      loadStore();
      state.typeId = guide().types[0].id;
      renderAll();
    });

    document.getElementById("type-nav").addEventListener("click", (event) => {
      const button = event.target.closest("[data-type]");
      if (!button) return;
      state.typeId = button.dataset.type;
      renderNav();
      renderPanel();
    });

    document.getElementById("type-panel").addEventListener("click", (event) => {
      const variantBtn = event.target.closest("[data-variant]");
      if (variantBtn) {
        state.variantId[state.channel + ":" + state.typeId] = variantBtn.dataset.variant;
        state.exampleIndex[`${state.channel}:${state.typeId}:${variantBtn.dataset.variant}`] = 0;
        renderPanel();
        return;
      }
      const exampleBtn = event.target.closest("[data-example]");
      if (exampleBtn) {
        const type = typeById(state.typeId);
        const variant = currentVariant(type);
        state.exampleIndex[`${state.channel}:${type.id}:${variant.id}`] = Number(exampleBtn.dataset.example);
        renderPanel();
        return;
      }
      if (event.target.id === "adopt-btn") {
        const type = typeById(state.typeId);
        state.decisions[type.id] = currentVariant(type).id;
        save();
        renderNav();
        renderPanel();
        renderDecisions();
      }
    });

    document.getElementById("decision-note").addEventListener("input", (event) => {
      state.note = event.target.value;
      save();
      document.getElementById("prompt-box").value = buildPrompt();
    });

    document.getElementById("copy-prompt").addEventListener("click", async () => {
      const text = document.getElementById("prompt-box").value;
      const status = document.getElementById("copy-status");
      try {
        await navigator.clipboard.writeText(text);
        status.textContent = "已複製。可以直接貼給之後上稿的 AI。";
      } catch (err) {
        document.getElementById("prompt-box").focus();
        document.getElementById("prompt-box").select();
        status.textContent = "瀏覽器沒有開放剪貼簿，請在文字框裡全選後複製。";
      }
    });

    window.addEventListener("hashchange", () => {
      readHash();
      renderAll();
    });

    readHash();
    loadStore();
    renderAll();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
