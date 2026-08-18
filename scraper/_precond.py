#!/usr/bin/env python3
"""前置条件检查。全新克隆第一次跑的时候，应该看到该干什么，而不是看到堆栈。"""
import sys
from pathlib import Path

STEPS = {
    "list":   ("data/*.json（收藏清单）",
               "先用 userscript/xhs-export.user.js 导出清单，放进 data/。见 README 第 0 步"),
    "raw":    ("data/raw/",             "先跑 python3 scraper/fetch.py"),
    "corpus": ("data/corpus.jsonl",     "先跑 python3 scraper/build_corpus.py"),
    "class":  ("data/classified.json",  "先跑 python3 scraper/classify.py"),
    "tree":   ("data/tree.json",        "先跑 python3 scraper/build_canvas.py"),
}


def need(root, key, extra=""):
    what, how = STEPS[key]
    p = root / {"raw": "data/raw", "corpus": "data/corpus.jsonl",
                "class": "data/classified.json", "tree": "data/tree.json"}.get(key, "data")
    ok = any(p.glob("*.json")) if key == "raw" else p.exists()
    if key == "list":
        ok = bool(list((root / "data").glob("*.json")))
    if not ok:
        sys.exit(f"\n缺少 {what}\n→ {how}\n{extra}")
    return p
