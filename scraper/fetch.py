#!/usr/bin/env python3
"""
Stage 1 — 批量抓取小红书笔记原始数据。

复用 chenxiachan/xhs-claude-skills 已验证的路径：
带 cookies 请求 explore 页 -> 解析 window.__INITIAL_STATE__ -> note 对象。

零第三方依赖（stdlib only）。可中断可续跑：已抓到的 id 直接跳过。

用法:
  python3 fetch.py                       # 抓全部未抓的
  python3 fetch.py --limit 20            # 先试 20 条
  python3 fetch.py --delay 2.5           # 调节间隔（默认 1.5~3.0 随机）
  python3 fetch.py --retry-failed        # 只重试上次失败的
"""
import argparse, json, os, random, re, ssl, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT      = Path(__file__).resolve().parent.parent
DATA      = ROOT / "data"
RAW       = DATA / "raw"
SUBS      = DATA / "subs"
LOG       = DATA / "fetch-log.jsonl"
COOKIES   = Path.home() / "cookies.json"
LIST_CAND = [DATA / "xhs-favorites-full.json",
             Path.home() / "Downloads" / "xhs-favorites-full.json",
             Path.home() / "Downloads" / "xhs-favorites.json"]

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# window.__INITIAL_STATE__ 里有 JS 的 undefined，JSON 解析不了。
# 原 skill 用 raw.replace('undefined','null')，会误伤正文里出现的 "undefined" 字样。
# 这里只替换处于「值」位置的 undefined。
UNDEF = re.compile(r'(?<=[:,\[])\s*undefined\s*(?=[,}\]])')
STATE = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*</script>', re.DOTALL)


def load_list():
    for p in LIST_CAND:
        if p.exists():
            d = json.loads(p.read_text())
            notes = d["notes"] if isinstance(d, dict) and "notes" in d else d
            print(f"[list] {p}  ->  {len(notes)} 条", file=sys.stderr)
            return notes, p
    sys.exit(f"找不到清单文件。请先用 userscript 导出，放到 {LIST_CAND[0]}")


def load_cookie_header():
    """cookies 是可选的。

    实测：带 xsec_token 的 explore 链接在未登录状态下也能拿到完整 __INITIAL_STATE__
    （正文、图片、视频 stream、字幕全都在）。原 skill 把 cookies 当硬前提，是过度要求。
    有 cookies 就带上（更稳），没有也照跑。
    """
    if not COOKIES.exists():
        print("[cookie] 未找到 ~/cookies.json —— 以未登录方式抓取（实测可行）", file=sys.stderr)
        return ""
    cs = json.loads(COOKIES.read_text())
    print(f"[cookie] 已加载 {len(cs)} 个 cookie", file=sys.stderr)
    return "; ".join(f"{c['name']}={c['value']}" for c in cs)


def fetch_one(url, cookie):
    req = urllib.request.Request(url)
    req.add_header("Cookie", cookie)
    req.add_header("User-Agent", UA)
    req.add_header("Accept-Language", "zh-CN,zh;q=0.9")
    req.add_header("Referer", "https://www.xiaohongshu.com/")
    with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
        return r.read().decode("utf-8", "ignore"), r.geturl()


def parse_note(html, note_id):
    m = STATE.search(html)
    if not m:
        return None, "no __INITIAL_STATE__"
    raw = UNDEF.sub(" null", m.group(1))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"json decode: {e}"
    ndm = (data.get("note") or {}).get("noteDetailMap") or {}
    if note_id in ndm and ndm[note_id].get("note"):
        return ndm[note_id]["note"], None
    for k, v in ndm.items():                       # key 偶尔不等于 note_id
        if isinstance(v, dict) and v.get("note"):
            return v["note"], None
    return None, f"noteDetailMap empty (keys={list(ndm)[:3]})"


def grab_subtitle(note, nid):
    """字幕 URL 带 sign+t 过期参数，必须在抓页面的同一趟里下下来。"""
    from build_corpus import pick_subtitle
    v = note.get("video") or {}
    if not v:
        return None
    url, lang = pick_subtitle(v)
    if not url:
        return None
    url = url.replace("http://", "https://", 1)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://www.xiaohongshu.com/")
    try:
        srt = urllib.request.urlopen(req, timeout=25, context=CTX).read().decode("utf-8", "ignore")
    except Exception as e:
        return f"ERR {type(e).__name__}"
    SUBS.mkdir(parents=True, exist_ok=True)
    (SUBS / f"{nid}.{lang}.srt").write_text(srt)
    return lang


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.0, help="固定间隔秒；0=1.5~3.0 随机")
    ap.add_argument("--retry-failed", action="store_true")
    a = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    SUBS.mkdir(parents=True, exist_ok=True)
    notes, _ = load_list()
    cookie = load_cookie_header()

    failed = set()
    if LOG.exists():
        for line in LOG.read_text().splitlines():
            try:
                r = json.loads(line)
                (failed.add if not r.get("ok") else failed.discard)(r["id"])
            except Exception:
                pass

    todo = []
    for n in notes:
        nid = n.get("id") or n.get("note_id")
        if not nid:
            continue
        if a.retry_failed:
            if nid in failed:
                todo.append(n)
        elif not (RAW / f"{nid}.json").exists():
            todo.append(n)
    if a.limit:
        todo = todo[: a.limit]

    done_already = len(list(RAW.glob("*.json")))
    print(f"[plan] 已有 {done_already} 条 / 本次待抓 {len(todo)} 条", file=sys.stderr)
    if not todo:
        return

    ok = err = 0
    logf = LOG.open("a")
    for i, n in enumerate(todo, 1):
        nid = n.get("id") or n.get("note_id")
        url = n.get("url") or (f"https://www.xiaohongshu.com/explore/{nid}"
                               f"?xsec_token={n.get('token','')}&xsec_source=pc_user")
        rec = {"id": nid, "title": n.get("title", "")}
        try:
            html, final = fetch_one(url, cookie)
            if "/login" in final:
                print("\n[FATAL] 被重定向到登录页 —— cookies 已失效，请重新导出 ~/cookies.json",
                      file=sys.stderr)
                break
            note, why = parse_note(html, nid)
            if note is None:
                rec.update(ok=False, err=why, html_len=len(html))
                err += 1
            else:
                (RAW / f"{nid}.json").write_text(
                    json.dumps({"_meta": n, "note": note}, ensure_ascii=False))
                rec.update(ok=True, sub=grab_subtitle(note, nid))
                ok += 1
        except urllib.error.HTTPError as e:
            rec.update(ok=False, err=f"HTTP {e.code}"); err += 1
        except Exception as e:
            rec.update(ok=False, err=f"{type(e).__name__}: {e}"); err += 1

        logf.write(json.dumps(rec, ensure_ascii=False) + "\n"); logf.flush()
        mark = "." if rec.get("ok") else "x"
        print(f"\r[{i}/{len(todo)}] ok={ok} err={err} {mark} {rec['title'][:24]:<24}",
              end="", file=sys.stderr)
        if i < len(todo):
            time.sleep(a.delay if a.delay else random.uniform(1.5, 3.0))

    logf.close()
    print(f"\n[done] ok={ok} err={err}  raw -> {RAW}", file=sys.stderr)


if __name__ == "__main__":
    main()
