#!/usr/bin/env python3
"""生成 Obsidian vault：笔记 stub + 分类 MOC + 实体页 + 总览。

有正文（corpus.jsonl）就写正文，没有就先出 stub，后面重跑会补上。
双链结构：笔记 -> 分类 / 实体，分类和实体页反向列出成员。图谱的边由实体产生。
"""
import json, re, sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
import taxonomy as CL
from _precond import need
from collections import Counter, defaultdict
import sys
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
VAULT = ROOT / "out" / "vault"
BAD   = re.compile(r'[\\/:*?"<>|#\[\]^]')


def likes(v):
    """点赞数格式不统一：'123' / '1.2万' / '100000+' / ''。统一成 int。"""
    t = str(v or "0").strip().replace("+", "").replace(",", "")
    mul = 1
    for suf, m in (("万", 10000), ("亿", 100000000), ("k", 1000), ("K", 1000)):
        if t.endswith(suf):
            t, mul = t[:-len(suf)], m
            break
    try:
        return int(float(t) * mul)
    except ValueError:
        return 0


def safe(name, maxlen=64):
    s = BAD.sub("", str(name)).strip().strip(".")
    s = re.sub(r"\s+", " ", s)
    return (s[:maxlen].strip() or "untitled")


def load():
    cls = json.loads((ROOT / "data" / "classified.json").read_text())
    corpus = {}
    cp = ROOT / "data" / "corpus.jsonl"
    if cp.exists():
        for line in cp.read_text().split("\n"):
            if line.strip():
                r = json.loads(line)
                corpus[r["id"]] = r
    return cls, corpus


def fm_list(xs):
    return "[" + ", ".join(f'"{x}"' for x in xs) + "]"


def main():
    need(ROOT, "class")
    cls, corpus = load()
    VAULT.mkdir(parents=True, exist_ok=True)
    for sub in ("笔记", "分类", "实体", "领域"):
        (VAULT / sub).mkdir(exist_ok=True)

    # 文件名去重
    used, fname = {}, {}
    for r in cls:
        base = safe(r["title"] or r["id"])
        n = used.get(base, 0)
        used[base] = n + 1
        fname[r["id"]] = base if n == 0 else f"{base} ({n+1})"

    by_cat = defaultdict(list)
    by_ent = defaultdict(list)

    for r in cls:
        nid = r["id"]
        c   = corpus.get(nid, {})
        cat = r["category"]
        ents = r["entities"]
        by_cat[cat].append(r)
        for e in ents:
            by_ent[e].append(r)

        desc = (c.get("text") or c.get("desc") or "").strip()
        tier = c.get("tier", "")
        links = " · ".join([f"[[{cat}]]"] + [f"[[{e}]]" for e in ents])
        tags = [f"xhs/{cat.replace(' ', '-')}"] + [f"实体/{e.replace(' ', '-')}" for e in ents]

        body = [
            "---",
            f'title: "{safe(r["title"], 120)}"',
            f'category: "{cat}"',
            f'author: "{safe(r.get("user",""), 40)}"',
            f'type: {r.get("type","")}',
            f'tier: {tier}',
            f'xhs_id: {nid}',
            f'liked: {r.get("liked","")}',
            f'tags: {fm_list(tags)}',
            "---",
            "",
            f"# {r['title']}",
            "",
            links,
            "",
            f"> {r.get('user','')} · {'视频' if r.get('type')=='video' else '图文'}"
            + (f" · {r.get('liked')} 赞" if r.get("liked") else "")
            + (f" · {int(c['video_duration'])//60000} 分钟" if c.get("video_duration") else ""),
            "",
        ]
        if desc:
            body += [desc, ""]
        elif tier:
            body += [f"*（正文待提取 · 档位 `{tier}`）*", ""]
        else:
            body += ["*（正文待提取）*", ""]

        if c.get("tags"):
            body += ["**原帖标签：** " + " ".join(f"#{t}" for t in c["tags"][:12]), ""]
        body += [f"[在小红书打开]({r.get('url','')})", ""]

        (VAULT / "笔记" / f"{fname[nid]}.md").write_text("\n".join(body))

    # 分类页
    for cat, rows in by_cat.items():
        rows = sorted(rows, key=lambda r: -likes(r.get("liked")))
        dom = next((d for d, cs in CL.DOMAIN if cat in cs), None)
        lines = [f"# {cat}", "", f"共 **{len(rows)}** 条。", "",
                 (f"[[{dom}]] · [[收藏总览]]" if dom else "[[收藏总览]]"), ""]
        if CL.SUMMARY.get(cat):
            lines += [CL.SUMMARY[cat], ""]
        vids = [r for r in rows if r.get("type") == "video"]
        if vids:
            lines.append(f"其中视频 {len(vids)} 条。")
            lines.append("")
        for r in rows:
            ent = " ".join(f"[[{e}]]" for e in r["entities"][:4])
            mark = "🎬" if r.get("type") == "video" else "📄"
            lines.append(f"- {mark} [[{fname[r['id']]}]] — {r.get('user','')} {ent}")
        (VAULT / "分类" / f"{safe(cat)}.md").write_text("\n".join(lines) + "\n")

    # 实体页
    for ent, rows in by_ent.items():
        cats = Counter(r["category"] for r in rows)
        lines = [f"# {ent}", "", f"被 **{len(rows)}** 条收藏提及。", "", "[[收藏总览]]", "",
                 "涉及分类：" + "、".join(f"[[{k}]]（{v}）" for k, v in cats.most_common()), ""]
        for r in sorted(rows, key=lambda r: r["category"]):
            mark = "🎬" if r.get("type") == "video" else "📄"
            lines.append(f"- {mark} [[{fname[r['id']]}]] — {r.get('user','')}")
        (VAULT / "实体" / f"{safe(ent)}.md").write_text("\n".join(lines) + "\n")

    # 领域页
    for dom, cats in CL.DOMAIN:
        cats = [c for c in cats if c in by_cat]
        if not cats:
            continue
        tot_d = sum(len(by_cat[c]) for c in cats)
        lines = [f"# {dom}", "", f"共 **{tot_d}** 条 · {len(cats)} 个分类", "", "[[收藏总览]]", ""]
        if CL.DOMAIN_SUMMARY.get(dom):
            lines += [CL.DOMAIN_SUMMARY[dom], "", "---", ""]
        for c in sorted(cats, key=lambda c: -len(by_cat[c])):
            lines.append(f"- [[{c}]] — {len(by_cat[c])} 条")
        (VAULT / "领域" / f"{safe(dom)}.md").write_text("\n".join(lines) + "\n")

    # 总览
    tot = len(cls)
    cc  = Counter(r["category"] for r in cls)
    ec  = Counter(e for r in cls for e in r["entities"])
    have = sum(1 for r in cls if corpus.get(r["id"], {}).get("text"))
    lines = [
        "# 收藏总览", "",
        f"小红书收藏 **{tot}** 条 · 已提取正文 **{have}** 条 · "
        f"图文 {sum(1 for r in cls if r.get('type')!='video')} / 视频 {sum(1 for r in cls if r.get('type')=='video')}",
        "", "## 分类", "", "| 分类 | 条数 | 占比 |", "|---|---:|---:|",
    ]
    for k, v in cc.most_common():
        lines.append(f"| [[{k}]] | {v} | {v/tot*100:.1f}% |")
    lines += ["", "## 高频实体", "", "| 实体 | 提及 |", "|---|---:|"]
    for k, v in ec.most_common(30):
        lines.append(f"| [[{k}]] | {v} |")
    (VAULT / "收藏总览.md").write_text("\n".join(lines) + "\n")

    print(f"vault -> {VAULT}")
    print(f"  笔记 {len(cls)} · 领域 {len(CL.DOMAIN)} · 分类 {len(by_cat)} · "
          f"实体 {len(by_ent)} · 有正文 {have}")


if __name__ == "__main__":
    main()
