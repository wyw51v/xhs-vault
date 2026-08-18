#!/usr/bin/env python3
"""对「待定·需正文」的条目，改用正文（desc + 字幕）重新分类。

标题判断不了不代表内容判断不了。同一套规则，喂更多文本。
仍然判断不了的，标 `待定·仍无解`——那才是真的需要人看一眼。
"""
import json
from collections import Counter
from pathlib import Path
import classify as C

ROOT = Path(__file__).resolve().parent.parent
UNSET_T = "待定·需正文"
UNSET_C = "待定·仍无解"


def main():
    cls = json.loads((ROOT / "data" / "classified.json").read_text())
    ovp = ROOT / "data" / "overrides.json"
    ov = {k: v for k, v in json.loads(ovp.read_text()).items()
          if not k.startswith("_")} if ovp.exists() else {}
    corpus = {}
    cp = ROOT / "data" / "corpus.jsonl"
    if cp.exists():
        for line in cp.read_text().split("\n"):
            if line.strip():
                r = json.loads(line)
                corpus[r["id"]] = r

    moved, still, nodata = 0, 0, 0
    for r in cls:
        # 实体永远用全文重算 —— 正文里的实体比标题多得多，图谱的边靠它
        c = corpus.get(r["id"], {})
        # 窗口太大会被正文里的零散词带偏（讲拖延的文章提一句开源就被判成工程）
        text = (c.get("text") or "")[:500]
        if text:
            r["entities"] = C.entities(f"{r.get('title','')} {r.get('user','')} "
                                       f"{(c.get('text') or '')[:4000]}")

        if r["category"] not in (UNSET_T, UNSET_C):
            continue
        if not text:
            r["category"] = UNSET_T
            nodata += 1
            continue
        cat = C.classify(f"{r.get('title','')} {text}")
        if cat == C.UNSET:
            r["category"] = UNSET_C
            still += 1
        else:
            r["category"] = cat
            r["by_content"] = True
            moved += 1

    hand = 0
    for r in cls:
        if r["id"] in ov:
            r["category"] = ov[r["id"]]
            r["by_hand"] = True
            hand += 1
    if hand:
        print(f"人工覆盖: {hand} 条", file=__import__("sys").stderr)

    (ROOT / "data" / "classified.json").write_text(json.dumps(cls, ensure_ascii=False, indent=1))

    cc = Counter(r["category"] for r in cls)
    tot = len(cls)
    print(f"靠正文归类成功: {moved}   正文也判断不了: {still}   还没抓到正文: {nodata}\n")
    print(f"{'分类':<20}{'数量':>5}{'占比':>8}")
    print("-" * 34)
    for k, v in cc.most_common():
        print(f"{k:<20}{v:>5}{v/tot*100:>7.1f}%")
    ec = Counter(e for r in cls for e in r["entities"])
    print(f"\n实体 top 20（已用全文重算）:")
    for k, v in ec.most_common(20):
        print(f"  {k:<14}{v:>4}")


if __name__ == "__main__":
    main()
