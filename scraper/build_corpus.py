#!/usr/bin/env python3
"""
Stage 1.5 — 把 data/raw/*.json 归一化成 corpus.jsonl，并给每篇打一个「处理档位」。

档位决定后续花多少钱。这一步不发任何网络请求、不调用任何模型。

档位:
  text-full     图文，desc 已是完整正文        -> 免费，已完成
  needs-ocr     图文，desc 短但图多            -> 需要 Claude 多模态读图
  thin          图文，desc 短且图少            -> 大概率无内容价值
  video-srt     视频，平台自带字幕             -> curl 一下即可，免费
  video-whisper 视频，无字幕                   -> 需本地转录，暂缓/只跑前 5 分钟
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW  = ROOT / "data" / "raw"
SUBS = ROOT / "data" / "subs"
OCRD = ROOT / "data" / "ocr"
OUT  = ROOT / "data" / "corpus.jsonl"

TOPIC = re.compile(r'#[^#\[\]]{1,40}\[话题\]#')     # #xxx[话题]# 标记
LONG_DESC = 400          # desc 超过这个字数 = 正文已完整
MANY_IMGS = 3


def deep_media(video):
    """video.media 有时是 dict，有时是 JSON 字符串；mediaV2 同理。逐个试。"""
    for key in ("media", "mediaV2"):
        m = video.get(key)
        if isinstance(m, str):
            try: m = json.loads(m)
            except Exception: continue
        if isinstance(m, dict):
            yield m


def pick_subtitle(video):
    """按 source > zh-CN > en-US 取字幕 URL。

    注意：字幕挂在 media.video.subtitles，不是 media.subtitles
    （chenxiachan 原 skill 的文档写的是后者，是错的）。
    结构: {"zh-CN":[{"url":..,"language":..}], "source":[..], "en-US":[..]}
    URL 带 sign + t 过期参数，抓到后应尽快下载。
    """
    for m in deep_media(video):
        for holder in (m.get("video"), m):
            if not isinstance(holder, dict):
                continue
            subs = holder.get("subtitles") or holder.get("subtitle")
            if not subs:
                continue
            by = {}
            if isinstance(subs, dict):
                for lang, arr in subs.items():
                    if isinstance(arr, dict):
                        arr = [arr]
                    if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                        u = arr[0].get("url") or arr[0].get("subtitleUrl")
                        if u:
                            by[lang] = u
            elif isinstance(subs, list):
                for s_ in subs:
                    if isinstance(s_, dict) and s_.get("url"):
                        by[s_.get("language") or s_.get("lang") or "?"] = s_["url"]
            for want in ("source", "zh-CN", "zh", "en-US", "en"):
                if want in by:
                    return by[want], want
            if by:
                k = next(iter(by))
                return by[k], k
    return None, None


def pick_stream(video):
    for m in deep_media(video):
        st = m.get("stream") or {}
        if isinstance(st, str):
            try: st = json.loads(st)
            except Exception: st = {}
        for codec in ("h264", "h265", "av1"):
            arr = st.get(codec) or []
            if isinstance(arr, list) and arr:
                u = arr[0].get("masterUrl") or arr[0].get("master_url")
                if u: return u, codec, arr[0].get("duration") or arr[0].get("videoDuration")
    return None, None, None


def srt_text(nid):
    """把 SRT 合成可读文本。

    小红书的字幕按帧切，一句话常被拆成好几条，且大多没有标点。
    直接空格拼接会得到一整块几万字的墙。这里按语义停顿重新分段：
    优先在句末标点断，否则累计到 ~110 字断一次。
    """
    hits = sorted(SUBS.glob(f"{nid}.*.srt"))
    if not hits:
        return None
    raw = hits[0].read_text(errors="ignore")
    cues, prev = [], None
    for ln in raw.split("\n"):
        t = ln.strip()
        if not t or t.isdigit() or "-->" in t:
            continue
        t = re.sub(r"<[^>]+>", "", t).strip()
        if t and t != prev:          # 同一句常被拆到相邻两帧，去重
            cues.append(t)
            prev = t
    if not cues:
        return None

    paras, buf = [], ""
    for c in cues:
        buf = (buf + " " + c).strip() if buf else c
        ends_sentence = c.endswith(("。", "！", "？", ".", "!", "?", "…"))
        if ends_sentence and len(buf) >= 40:
            paras.append(buf); buf = ""
        elif len(buf) >= 110:        # 无标点的口语字幕，按长度兜底
            paras.append(buf); buf = ""
    if buf:
        paras.append(buf)
    return "\n\n".join(paras).strip() or None


def ocr_text(nid):
    f = OCRD / f"{nid}.txt"
    if not f.exists():
        return None
    t = f.read_text(errors="ignore").strip()
    return t or None


sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxonomy import OCR_P1, OCR_P2

CATS = {}
_cp = ROOT / "data" / "classified.json"
if _cp.exists():
    for _r in json.loads(_cp.read_text()):
        CATS[_r["id"]] = _r.get("category", "")


def norm(rec):
    n, meta = rec["note"], rec.get("_meta", {})
    nid  = meta.get("id") or n.get("noteId") or n.get("note_id")
    desc = TOPIC.sub("", n.get("desc") or "").strip()
    typ  = (n.get("type") or meta.get("type") or "").lower()
    tags = [t.get("name") for t in (n.get("tagList") or []) if isinstance(t, dict) and t.get("name")]
    imgs = []
    for im in (n.get("imageList") or []):
        u = im.get("urlDefault") or im.get("url")
        if u: imgs.append(u.replace("http://", "https://", 1))
    user = n.get("user") or {}
    ii   = n.get("interactInfo") or {}
    video = n.get("video") or {}

    sub_url = sub_lang = stream = codec = dur = None
    if typ == "video" and video:
        sub_url, sub_lang = pick_subtitle(video)
        stream, codec, dur = pick_stream(video)
        if sub_url: sub_url = sub_url.replace("http://", "https://", 1)

    sub_text = srt_text(nid)
    ocr = ocr_text(nid)
    if typ == "video":
        tier = "video-srt" if (sub_url or sub_text) else "video-whisper"
    elif len(desc) >= LONG_DESC:
        tier = "text-full"
    elif len(imgs) >= MANY_IMGS:
        tier = "needs-ocr"
    else:
        tier = "thin"

    # 统一正文：图文用 desc，视频用 desc + 字幕。OCR 结果后续再并进来。
    parts = [desc] if desc else []
    if sub_text:
        parts.append(sub_text)
    if ocr:
        parts.append(ocr)
    text = "\n\n".join(parts)

    cat = CATS.get(nid, "")
    if tier == "needs-ocr" and ocr:
        tier = "ocr-done"
    if tier == "needs-ocr":
        ocr_p = 1 if cat in OCR_P1 else (2 if cat in OCR_P2 else 3)
    else:
        ocr_p = 0

    return {
        "id": nid,
        "category": cat,
        "ocr_priority": ocr_p,
        "text": text,
        "text_len": len(text),
        "title": (n.get("title") or meta.get("title") or "").strip(),
        "type": typ,
        "tier": tier,
        "desc": desc,
        "desc_len": len(desc),
        "tags": tags,
        "author": user.get("nickname") or meta.get("user") or "",
        "author_id": user.get("userId") or user.get("user_id") or "",
        "time": n.get("time"),
        "ip": n.get("ipLocation") or "",
        "images": imgs,
        "n_images": len(imgs),
        "video_duration": dur,
        "subtitle_url": sub_url,
        "subtitle_lang": sub_lang,
        "subtitle_text": sub_text,
        "subtitle_len": len(sub_text or ""),
        "ocr_text": ocr,
        "ocr_len": len(ocr or ""),
        "video_stream": stream,
        "video_codec": codec,
        "liked": (ii.get("likedCount") or meta.get("liked") or ""),
        "collected": ii.get("collectedCount") or "",
        "comments": ii.get("commentCount") or "",
        "url": meta.get("url") or f"https://www.xiaohongshu.com/explore/{nid}",
    }


def main():
    files = sorted(RAW.glob("*.json"))
    if not files:
        sys.exit(f"{RAW} 为空 —— 先跑 fetch.py")
    rows, bad = [], 0
    for f in files:
        try:
            rows.append(norm(json.loads(f.read_text())))
        except Exception as e:
            bad += 1
            print(f"[skip] {f.name}: {type(e).__name__}: {e}", file=sys.stderr)

    # json.dumps 不转义 U+2028/U+2029，但 str.splitlines() 会在它们上断行 -> JSONL 被切碎。
    def dump(r):
        return (json.dumps(r, ensure_ascii=False)
                .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    OUT.write_text("\n".join(dump(r) for r in rows))

    from collections import Counter
    c = Counter(r["tier"] for r in rows)
    order = ["text-full", "video-srt", "ocr-done", "needs-ocr", "video-whisper", "thin"]
    cost  = {"text-full": "免费 · 已完成", "video-srt": "免费 · 平台字幕",
             "ocr-done": "免费 · 本地 Vision OCR", "needs-ocr": "待 OCR",
             "video-whisper": "本地转录 · 暂缓", "thin": "正文短、图少"}
    print(f"\n共 {len(rows)} 篇（解析失败 {bad}）  -> {OUT}\n", file=sys.stderr)
    print(f"{'档位':<15}{'数量':>6}   后续成本", file=sys.stderr)
    print("-" * 46, file=sys.stderr)
    for t in order:
        if c[t]: print(f"{t:<15}{c[t]:>6}   {cost[t]}", file=sys.stderr)
    print(f"\nOCR 分优先级（只有 P1/P2 值得读，P3 是照片贴）:", file=sys.stderr)
    for p, lbl in ((1, "P1 知识类"), (2, "P2 攻略类"), (3, "P3 照片贴·跳过")):
        rs = [r for r in rows if r.get("ocr_priority") == p]
        if rs:
            print(f"  P{p} {lbl:<12} {len(rs):>3} 篇 / {sum(r['n_images'] for r in rs):>4} 张图",
                  file=sys.stderr)
    ocr_n = sum(1 for r in rows if r.get("ocr_text"))
    ocr_c = sum(r.get("ocr_len", 0) for r in rows)
    if ocr_n:
        print(f"OCR 已落地: {ocr_n} 篇 / {ocr_c:,} 字", file=sys.stderr)
    tot_c = sum(r.get("text_len", 0) for r in rows)
    print(f"语料合计: {tot_c:,} 字", file=sys.stderr)
    subs_n = sum(1 for r in rows if r.get("subtitle_text"))
    subs_c = sum(r.get("subtitle_len", 0) for r in rows)
    if subs_n:
        print(f"字幕已落地: {subs_n} 篇 / {subs_c:,} 字", file=sys.stderr)
    secs = sum(int(r["video_duration"] or 0) for r in rows if r["tier"] == "video-whisper")
    if secs: print(f"video-whisper 总时长: {secs//60000} 分钟（{secs//3600000} 小时）", file=sys.stderr)


if __name__ == "__main__":
    main()
