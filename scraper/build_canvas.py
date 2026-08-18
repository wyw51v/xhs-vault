#!/usr/bin/env python3
"""四层树 canvas：根 → 领域 → 分类 → 子簇 → 笔记。

产出：
  out/vault/收藏夹.canvas   Obsidian 原生 Canvas，节点可拖动
  data/tree.json            供 HTML 看板渲染
"""
import json, re, sys
from collections import defaultdict
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import taxonomy as CL
from _precond import need

ROOT = Path(__file__).resolve().parent.parent
BAD  = re.compile(r'[\\/:*?"<>|#\[\]^]')


def safe(name, maxlen=64):
    s = BAD.sub("", str(name)).strip().strip(".")
    return (re.sub(r"\s+", " ", s)[:maxlen].strip() or "untitled")


def build_tree():
    cls = json.loads((ROOT / "data" / "classified.json").read_text())
    corpus = {}
    cp = ROOT / "data" / "corpus.jsonl"
    if cp.exists():
        for line in cp.read_text().split("\n"):
            if line.strip():
                r = json.loads(line)
                corpus[r["id"]] = r

    used, fname = {}, {}
    for r in cls:
        b = safe(r["title"] or r["id"])
        n = used.get(b, 0); used[b] = n + 1
        fname[r["id"]] = b if n == 0 else f"{b} ({n+1})"

    by_cat = defaultdict(list)
    for r in cls:
        by_cat[r["category"]].append(r)

    def stat(rows):
        v = sum(1 for r in rows if r.get("type") == "video")
        return (len(rows),
                sum(corpus.get(r["id"], {}).get("text_len", 0) for r in rows),
                v, len(rows) - v)

    def cat_node(cat):
        rows = by_cat[cat]
        subdefs = CL.SUB.get(cat, [])
        subs = defaultdict(list)
        for r in rows:
            # 只看标题：作者名和实体标签会把子簇判断带偏
            # （「成本可降到Hermes的1/6」带了 Codex 实体，就被吸进 Claude Code 配置）
            blob = r.get("title", "")
            hit = "其他"
            for name, pat in subdefs:
                if re.search(pat, blob, re.I):
                    hit = name
                    break
            subs[hit].append(r)
        order = [n for n, _ in subdefs if n in subs] + (["其他"] if "其他" in subs else [])
        n, ch, v, im = stat(rows)
        return {
            "name": cat, "n": n, "chars": ch, "video": v, "img": im,
            "summary": CL.SUMMARY.get(cat, ""),
            "subs": [{
                "name": sn, "n": len(subs[sn]),
                "notes": [{
                    "id": r["id"], "t": r["title"], "u": r.get("user", ""),
                    "v": r.get("type") == "video",
                    "len": corpus.get(r["id"], {}).get("text_len", 0),
                    "f": fname[r["id"]], "url": r.get("url", ""),
                } for r in sorted(subs[sn],
                                  key=lambda r: -corpus.get(r["id"], {}).get("text_len", 0))],
            } for sn in order],
        }

    tree, claimed = [], set()
    for dom, cats in CL.DOMAIN:
        cats = [c for c in cats if c in by_cat]
        claimed |= set(cats)
        rows = [r for c in cats for r in by_cat[c]]
        n, ch, v, im = stat(rows)
        tree.append({"name": dom, "n": n, "chars": ch, "video": v, "img": im,
                     "summary": CL.DOMAIN_SUMMARY.get(dom, ""),
                     "cats": [cat_node(c) for c in
                              sorted(cats, key=lambda c: -len(by_cat[c]))]})
    rest = [c for c in by_cat if c not in claimed]
    if rest:
        rows = [r for c in rest for r in by_cat[c]]
        n, ch, v, im = stat(rows)
        tree.append({"name": "其他", "n": n, "chars": ch, "video": v, "img": im,
                     "summary": "没能归入以上领域的零头。",
                     "cats": [cat_node(c) for c in rest]})
    return tree


COLORS = ["1", "2", "3", "4", "5", "6"]


def to_canvas(tree):
    """Obsidian Canvas：领域 / 分类 / 子簇 三列，笔记以 [[链接]] 列在子簇节点里。"""
    nodes, edges = [], []
    XR, XD, XC, XS = 0, 520, 1060, 1660
    y = 0
    total = sum(d["n"] for d in tree)
    total_ch = sum(d["chars"] for d in tree)

    for di, dom in enumerate(tree):
        col = COLORS[di % len(COLORS)]
        did = f"d{di}"
        dom_y0 = y
        cat_centers = []

        for ci, cat in enumerate(dom["cats"]):
            cid = f"d{di}c{ci}"
            cat_y0 = y
            sub_centers = []
            for si, sub in enumerate(cat["subs"]):
                lines = [f"- [[{n['f']}]]" for n in sub["notes"][:40]]
                if len(sub["notes"]) > 40:
                    lines.append(f"- …另 {len(sub['notes'])-40} 条")
                h = max(110, 74 + 24 * len(lines))
                sid = f"{cid}s{si}"
                nodes.append({"id": sid, "type": "text", "x": XS, "y": y,
                              "width": 620, "height": h, "color": col,
                              "text": f"#### {sub['name']} · {sub['n']}\n\n" + "\n".join(lines)})
                edges.append({"id": f"e{cid}-{sid}", "fromNode": cid, "fromSide": "right",
                              "toNode": sid, "toSide": "left"})
                sub_centers.append(y + h / 2)
                y += h + 36

            blk = max(y - cat_y0 - 36, 150)
            summ = cat["summary"] or ""
            chh = max(180, 132 + 22 * (len(summ) // 24 + 1))
            cy = cat_y0 + blk / 2 - chh / 2
            nodes.append({"id": cid, "type": "text", "x": XC, "y": int(cy),
                          "width": 440, "height": int(chh), "color": col,
                          "text": f"### {cat['name']}\n\n**{cat['n']} 条** · {cat['img']} 图文 · "
                                  f"{cat['video']} 视频\n\n{summ}"})
            edges.append({"id": f"e{did}-{cid}", "fromNode": did, "fromSide": "right",
                          "toNode": cid, "toSide": "left"})
            cat_centers.append(cy + chh / 2)
            y = max(y, cat_y0 + chh + 50)

        dblk = max(y - dom_y0 - 50, 170)
        ds = dom["summary"] or ""
        dh = max(200, 140 + 22 * (len(ds) // 22 + 1))
        dy = dom_y0 + dblk / 2 - dh / 2
        nodes.append({"id": did, "type": "text", "x": XD, "y": int(dy),
                      "width": 460, "height": int(dh), "color": col,
                      "text": f"## {dom['name']}\n\n**{dom['n']} 条** · {len(dom['cats'])} 分类 · "
                              f"{dom['img']} 图文 · {dom['video']} 视频\n\n{ds}"})
        edges.append({"id": f"eroot-{did}", "fromNode": "root", "fromSide": "right",
                      "toNode": did, "toSide": "left"})
        y += 110

    rh = 240
    nodes.insert(0, {"id": "root", "type": "text", "x": XR, "y": 0,
                     "width": 440, "height": rh, "color": "6",
                     "text": f"# 小红书收藏夹\n\n**{total}** 条 · {len(tree)} 个领域\n\n"
                             f"正文已提取 {total_ch:,} 字\n\n[[收藏总览]]"})
    return {"nodes": nodes, "edges": edges}


def main():
    need(ROOT, "class")
    tree = build_tree()
    (ROOT / "data" / "tree.json").write_text(json.dumps(tree, ensure_ascii=False))
    canvas = to_canvas(tree)
    (ROOT / "out" / "vault" / "收藏夹.canvas").write_text(
        json.dumps(canvas, ensure_ascii=False, indent=1))
    nc = sum(len(d["cats"]) for d in tree)
    ns = sum(len(c["subs"]) for d in tree for c in d["cats"])
    print(f"tree: {len(tree)} 领域 / {nc} 分类 / {ns} 子簇 / {sum(d['n'] for d in tree)} 条")
    print(f"canvas: {len(canvas['nodes'])} 节点 {len(canvas['edges'])} 边")
    for d in tree:
        print(f"\n  {d['name']}  {d['n']} 条")
        for c in d["cats"]:
            print(f"    {c['name']:<16}{c['n']:>4}  " +
                  " | ".join(f"{s['name']}({s['n']})" for s in c["subs"]))


if __name__ == "__main__":
    main()
