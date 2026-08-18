#!/usr/bin/env python3
"""按标题分类 + 抽实体。引擎部分，规则在 taxonomy.py。

规则有序，先匹配先得；全部大小写不敏感。

落到「待定·需正文」的不是失败——那是精确圈出「靠标题判断不了、必须抓正文」的子集，
是 Stage 2 的优先队列。
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNSET = "待定·需正文"

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxonomy import CATEGORIES as RULES, ENTITIES, OWN_AUTHOR, OWN_CATEGORY
from _precond import need

def fix_wb(p):
    # \b 在中文旁边不成立（Python 里 CJK 也算 \w），会漏掉「多Agent协作」这类。
    # 换成只排除 ASCII 字母数字的 lookaround。
    p = re.sub(r'\\b([a-z0-9])', r'(?<![a-z0-9])\1', p)
    p = re.sub(r'([a-z0-9])\\b', r'\1(?![a-z0-9])', p)
    return p

F = re.IGNORECASE
# 规则可写成 (名字, 正模式) 或 (名字, 正模式, 负模式)。
# 负模式解决「含有某词、但讲的不是那件事」——比如标题里有 Claude Code，
# 但整条其实是创始人访谈，那属于行业观察而非工程实践。
RULES_C = [(r[0], re.compile(fix_wb(r[1]), F),
            re.compile(fix_wb(r[2]), F) if len(r) > 2 else None) for r in RULES]
ENT_C   = {n: re.compile(fix_wb(p), F) for n, p in ENTITIES.items()}


def classify(text):
    for name, rx, neg in RULES_C:
        if rx.search(text) and not (neg and neg.search(text)):
            return name
    return UNSET


def entities(text):
    return sorted(n for n, rx in ENT_C.items() if rx.search(text))


def main():
    need(ROOT, "list")
    cand = [ROOT / "data" / "xhs-favorites-full.json"] + \
           sorted((ROOT / "data").glob("xhs-favorites*.json"))
    src = next((c for c in cand if c.exists()), None)
    if src is None:
        need(ROOT, "list")
    d = json.load(open(src))
    notes = d["notes"] if isinstance(d, dict) and "notes" in d else d
    print(f"[list] {src.name} -> {len(notes)} 条", file=sys.stderr)
    out = []
    for n in notes:
        title, user = n.get("title", ""), n.get("user", "")
        # 分类只看标题。小红书博主名里常塞主题词（「XX的开源人生」「XX出海圈」），
        # 混进分类依据会把整条带偏 —— 详见 docs/分类调优.md 第三条。
        own = bool(OWN_AUTHOR) and bool(re.search(OWN_AUTHOR, user, re.I))
        cat = OWN_CATEGORY if own else classify(title)
        # 实体可以看作者——那是「这条跟谁有关」，作者本身就是答案之一
        out.append({**n, "category": cat, "entities": entities(f"{title} {user}")})
    (ROOT / "data" / "classified.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))

    from collections import Counter
    c = Counter(r["category"] for r in out)
    e = Counter(x for r in out for x in r["entities"])
    tot = len(out)
    print(f"{'分类':<20}{'数量':>5}{'占比':>8}")
    print("-" * 34)
    for k, v in c.most_common():
        print(f"{k:<20}{v:>5}{v/tot*100:>7.1f}%")
    print(f"\n实体 top 30:")
    for k, v in e.most_common(30):
        print(f"  {k:<14}{v:>4}")
    print(f"\n无实体条目: {sum(1 for r in out if not r['entities'])}")


if __name__ == "__main__":
    main()
