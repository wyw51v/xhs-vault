#!/usr/bin/env python3
"""实体共现图：两个实体出现在同一篇收藏里就连一条边，权重=共现次数。

布局用 Fruchterman-Reingold 在本地算好（确定性，不依赖浏览器端模拟）。
输出 data/graph.json 供看板渲染。
"""
import json, math, random
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_NODE = 2      # 至少被 2 篇提及才进图
MIN_EDGE = 2      # 至少共现 2 次才连边


def layout(nodes, edges, iters=600, seed=7):
    rnd = random.Random(seed)
    n = len(nodes)
    pos = {i: [rnd.uniform(-1, 1), rnd.uniform(-1, 1)] for i in range(n)}
    k = math.sqrt(1.0 / max(n, 1))
    adj = defaultdict(list)
    for a, b, w in edges:
        adj[a].append((b, w))
        adj[b].append((a, w))
    t = 0.12
    for it in range(iters):
        disp = {i: [0.0, 0.0] for i in range(n)}
        for i, j in combinations(range(n), 2):          # 斥力
            dx = pos[i][0] - pos[j][0]
            dy = pos[i][1] - pos[j][1]
            d2 = dx * dx + dy * dy + 1e-9
            f = k * k / d2
            disp[i][0] += dx * f; disp[i][1] += dy * f
            disp[j][0] -= dx * f; disp[j][1] -= dy * f
        for a, b, w in edges:                            # 引力
            dx = pos[a][0] - pos[b][0]
            dy = pos[a][1] - pos[b][1]
            d = math.sqrt(dx * dx + dy * dy) + 1e-9
            f = (d * d / k) * math.log1p(w) * 0.05
            disp[a][0] -= dx / d * f; disp[a][1] -= dy / d * f
            disp[b][0] += dx / d * f; disp[b][1] += dy / d * f
        for i in range(n):                               # 位移 + 退火
            dx, dy = disp[i]
            d = math.sqrt(dx * dx + dy * dy) + 1e-9
            pos[i][0] += dx / d * min(d, t)
            pos[i][1] += dy / d * min(d, t)
        t *= 0.995
    xs = [p[0] for p in pos.values()]; ys = [p[1] for p in pos.values()]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    sx = (x1 - x0) or 1; sy = (y1 - y0) or 1
    return {i: [(pos[i][0] - x0) / sx, (pos[i][1] - y0) / sy] for i in range(n)}


def main():
    cls = json.loads((ROOT / "data" / "classified.json").read_text())
    cnt = Counter(e for r in cls for e in r["entities"])
    keep = {e for e, c in cnt.items() if c >= MIN_NODE}

    pair = Counter()
    for r in cls:
        es = sorted(set(r["entities"]) & keep)
        for a, b in combinations(es, 2):
            pair[(a, b)] += 1

    names = sorted(keep, key=lambda e: -cnt[e])
    idx = {e: i for i, e in enumerate(names)}
    edges = [(idx[a], idx[b], w) for (a, b), w in pair.items() if w >= MIN_EDGE]

    # 主分类：该实体最常出现在哪个分类下
    home = {}
    for e in names:
        c = Counter(r["category"] for r in cls if e in r["entities"])
        home[e] = c.most_common(1)[0][0] if c else ""

    pos = layout(names, edges)
    g = {
        "nodes": [{"n": e, "c": cnt[e], "cat": home[e],
                   "x": round(pos[i][0], 4), "y": round(pos[i][1], 4)}
                  for i, e in enumerate(names)],
        "edges": [{"a": a, "b": b, "w": w} for a, b, w in edges],
    }
    (ROOT / "data" / "graph.json").write_text(json.dumps(g, ensure_ascii=False))
    print(f"graph: {len(names)} 节点 / {len(edges)} 边  -> data/graph.json")
    print("\n共现最强的 15 对:")
    for (a, b), w in pair.most_common(15):
        print(f"  {w:>3}  {a} — {b}")


if __name__ == "__main__":
    main()
