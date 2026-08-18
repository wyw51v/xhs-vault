#!/usr/bin/env python3
"""对图文笔记做 OCR：下图 -> macOS Vision 识别 -> data/ocr/{id}.txt

只处理 ocr_priority 1/2（知识类与攻略类）。P3 是照片贴，图里没字，跳过。
可中断可续跑。图片下完即删，不占盘。
"""
import argparse, json, os, shutil, ssl, subprocess, sys, tempfile, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OCR  = ROOT / "data" / "ocr"
BIN  = ROOT / "tools" / "ocr"
UA   = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def grab(args):
    url, path = args
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", UA)
        req.add_header("Referer", "https://www.xiaohongshu.com/")
        with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
            Path(path).write_bytes(r.read())
        return path
    except Exception:
        return None


def run_ocr(paths):
    out = subprocess.run([str(BIN)] + paths, capture_output=True, text=True, timeout=600)
    blocks, cur = [], None
    for line in out.stdout.split("\n"):
        if line.startswith("---FILE---"):
            cur = []
            blocks.append(cur)
        elif cur is not None and line.strip() and not line.startswith("__ERR__"):
            cur.append(line)
    return blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-priority", type=int, default=2)
    ap.add_argument("--cap", type=int, default=40, help="每篇最多处理多少张图")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    if not BIN.exists():
        sys.exit(f"缺少 {BIN}，先编译: swiftc -O -o tools/ocr tools/ocr.swift "
                 f"-framework Vision -framework AppKit")
    OCR.mkdir(parents=True, exist_ok=True)

    rows = [json.loads(l) for l in (ROOT / "data" / "corpus.jsonl").read_text().split("\n") if l.strip()]
    todo = [r for r in rows
            if 1 <= (r.get("ocr_priority") or 0) <= a.max_priority
            and r["images"] and not (OCR / f"{r['id']}.txt").exists()]
    todo.sort(key=lambda r: (r.get("ocr_priority", 9), -r["n_images"]))
    if a.limit:
        todo = todo[: a.limit]

    print(f"[plan] 待 OCR {len(todo)} 篇 / {sum(min(r['n_images'], a.cap) for r in todo)} 张图",
          file=sys.stderr)

    total_chars = 0
    for i, r in enumerate(todo, 1):
        d = tempfile.mkdtemp(prefix="xhsocr_")
        try:
            urls = r["images"][: a.cap]
            jobs = [(u, os.path.join(d, f"{j:03d}.jpg")) for j, u in enumerate(urls)]
            with ThreadPoolExecutor(max_workers=4) as ex:
                paths = [p for p in ex.map(grab, jobs) if p]
            if not paths:
                (OCR / f"{r['id']}.txt").write_text("")
                continue
            blocks = run_ocr(paths)
            # 跨图断句：上一张最后一行常和下一张第一行是同一句
            pages = ["\n".join(b).strip() for b in blocks]
            text = "\n".join(p for p in pages if p)
            (OCR / f"{r['id']}.txt").write_text(text)
            total_chars += len(text)
            print(f"\r[{i}/{len(todo)}] {len(paths):>2}图 {len(text):>5}字 累计{total_chars:>7}  "
                  f"{r['title'][:22]:<22}", end="", file=sys.stderr)
        except Exception as e:
            print(f"\n[err] {r['id']} {type(e).__name__}: {e}", file=sys.stderr)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print(f"\n[done] OCR 文本 -> {OCR}  累计 {total_chars:,} 字", file=sys.stderr)


if __name__ == "__main__":
    main()
