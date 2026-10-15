#!/usr/bin/env python3
"""build_videos_json.py — YouTube チャンネルの新着から、サイトのスライダー用 videos.json を作る.

GitHub Actions から 6 時間ごとに実行する (.github/workflows/youtube-videos.yml).
API キーは使わない. 読むのは次の 2 つだけ.
  1. チャンネルの RSS (新しい順に最大 15 本. 前回の videos.json と合わせて, 本編を新しい順に最大 10 本残す)
  2. 各動画の再生ページ (長さを取るため. 取れなければ長さは出さない)

ショートは出さない. RSS のリンクが /shorts/ のもの, または /shorts/{id} が
リダイレクトせずに開けるものをショートとみなす.

タグ (カードの灰色のラベル) とタイトルの決め方:
  - タイトルが「本題｜シリーズ名」で, シリーズ名が overrides.json の series に入っていれば,
    タグ = シリーズ名, タイトル = 本題
  - それ以外は, タグ = overrides.json の default_tag, タイトル = RSS のタイトルそのまま
  - overrides.json の videos に動画IDごとの tag / title / hide を書けば, それが優先

使い方 (手元で試すとき):
  python3 site/youtube/build_videos_json.py            # site/youtube/videos.json を書く
  python3 site/youtube/build_videos_json.py --dry-run  # 書かずに表示だけ
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHANNEL_ID = "UC3vr_5p9kJch9zCMb44_rsQ"   # @PixelstoMotors
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
MAX_VIDEOS = 10
HERE = Path(__file__).resolve().parent
OUT = HERE / "videos.json"
OVERRIDES = HERE / "overrides.json"
JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (compatible; pixelstomotors-site-bot/1.0)"
NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def fetch(url: str, timeout: float = 20.0) -> tuple[int, str, str]:
    """(status, final_url, body) を返す. リダイレクトは追う."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.geturl(), r.read().decode("utf-8", errors="replace")


def is_short(video_id: str, link: str) -> bool:
    if "/shorts/" in link:
        return True
    try:
        status, final_url, _ = fetch(f"https://www.youtube.com/shorts/{video_id}")
    except Exception:
        return False        # 判定できないときは本編として扱う
    return status == 200 and "/shorts/" in final_url


def duration_text(video_id: str) -> str | None:
    """再生ページの approxDurationMs から, YouTube の表示 (例 13:36) と同じ長さの文字を作る.
    表示は「ミリ秒を秒に切り捨てて +1」と一致した (2026-10-15 に 6 本で確認)."""
    try:
        _, _, html = fetch(f"https://www.youtube.com/watch?v={video_id}")
    except Exception:
        return None
    ms = [int(x) for x in re.findall(r'"approxDurationMs":"(\d+)"', html)]
    if ms:
        s = max(ms) // 1000 + 1
    else:
        m = re.search(r'"lengthSeconds":"(\d+)"', html)
        if not m:
            return None
        s = int(m.group(1))
    h, rest = divmod(s, 3600)
    mnt, sec = divmod(rest, 60)
    return f"{h}:{mnt:02d}:{sec:02d}" if h else f"{mnt}:{sec:02d}"


def load_overrides() -> dict:
    if OVERRIDES.exists():
        return json.loads(OVERRIDES.read_text(encoding="utf-8"))
    return {}


def split_title(title: str, series: list[str], default_tag: str) -> tuple[str, str]:
    for sep in ("｜", "|"):
        if sep in title:
            head, tail = title.rsplit(sep, 1)
            if tail.strip() in series:
                return head.strip(), tail.strip()
    return title.strip(), default_tag


def build(previous: dict) -> dict:
    ov = load_overrides()
    series = ov.get("series", [])
    default_tag = ov.get("default_tag", "")
    per_video = ov.get("videos", {})
    desc = ov.get("description", "")
    prev_by_id = {v["id"]: v for v in previous.get("videos", [])}

    _, _, xml_text = fetch(FEED_URL)
    root = ET.fromstring(xml_text)
    videos = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", default="", namespaces=NS)
        if not vid:
            continue
        link_el = e.find("a:link", NS)
        link = link_el.get("href", "") if link_el is not None else ""
        o = per_video.get(vid, {})
        if o.get("hide"):
            continue
        if vid in prev_by_id and prev_by_id[vid].get("is_short") is not None:
            short = prev_by_id[vid]["is_short"]          # 一度判定した動画は聞き直さない
        else:
            short = is_short(vid, link)
        if short:
            continue
        raw_title = e.findtext("a:title", default="", namespaces=NS)
        title, tag = split_title(raw_title, series, default_tag)
        published = datetime.fromisoformat(e.findtext("a:published", default="", namespaces=NS))
        dur = prev_by_id.get(vid, {}).get("duration") or duration_text(vid)
        videos.append({
            "id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "thumb": f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg",
            "thumb_fallback": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "title": o.get("title", title),
            "tag": o.get("tag", tag),
            "date": published.astimezone(JST).strftime("%Y/%m/%d"),
            "published": published.isoformat(),
            "duration": o.get("duration", dur),
            "description": o.get("description", desc),
            "is_short": False,
        })
    # RSS は新しい 15 本だけで, ショートが多いと本編が数本しか入らない.
    # 前回の videos.json にあって今回の RSS から外れた本編は, そのまま残す (hide 指定は除く).
    seen = {v["id"] for v in videos}
    for v in previous.get("videos", []):
        if v["id"] not in seen and not per_video.get(v["id"], {}).get("hide"):
            videos.append(v)
    videos.sort(key=lambda v: v["published"], reverse=True)
    videos = videos[:MAX_VIDEOS]
    return {"channel_url": "https://www.youtube.com/@PixelstoMotors", "videos": videos}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    previous = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    try:
        data = build(previous)
    except (urllib.error.URLError, ET.ParseError) as e:
        print(f"[ERROR] RSS を読めなかった. videos.json は変えない: {e}", file=sys.stderr)
        return 1
    if not data["videos"]:
        print("[ERROR] 本編が1本も取れなかった. videos.json は変えない", file=sys.stderr)
        return 1
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.dry_run:
        print(text)
        return 0
    if OUT.exists() and OUT.read_text(encoding="utf-8") == text:
        print("[OK] 変更なし")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"[OK] {len(data['videos'])} 本を書いた → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
