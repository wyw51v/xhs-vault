#!/usr/bin/env python3
"""收藏夹检索：BM25 打底。

中文没有分词器可用（未装 jieba），改用字符二元组（bigram）建索引——
对中文检索效果接近词级，且零依赖。英文按词切。
"""
import json, math, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
K1, B = 1.5, 0.75

_CJK = re.compile(r"[一-鿿]")
_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9_+.#-]*|\d+")


# 问句里的口语填充词。不滤掉的话，「我想给独立站做海外冷启动，收藏夹里有哪些
# 能直接用的方法？」会产生一堆噪音 bigram，把不相关的笔记顶上来。
STOP = ("收藏夹 我想 我要 有没有 有哪些 哪些 能直接用 直接用 方法 帮我 请问 一下 "
        "什么 怎么 如何 为什么 是不是 可以 应该 需要 想找 找一下 关于 的内容 内容 "
        "相关 推荐 告诉我 看看 里面 有关 这个 那个 一些 比较 之类 等等").split()
STOP_RE = re.compile("|".join(sorted(STOP, key=len, reverse=True)))


def clean_query(q):
    q = STOP_RE.sub(" ", q)
    return re.sub(r"[，。？！、；：“”‘’《》()（）\s]+", " ", q).strip()


def tokenize(text):
    text = text.lower()
    toks = _WORD.findall(text)
    cjk = "".join(c if _CJK.match(c) else " " for c in text)
    for run in cjk.split():
        if len(run) == 1:
            toks.append(run)
        else:
            toks += [run[i:i+2] for i in range(len(run) - 1)]
    return toks


class Index:
    def __init__(self, docs):
        """docs: [{id, title, text, ...}]"""
        self.docs = docs
        self.tf, self.len = [], []
        self.df = Counter()
        for d in docs:
            # 标题权重更高：重复三次参与统计
            toks = tokenize(f"{d['title']} {d['title']} {d['title']} "
                            f"{d.get('author','')} {d.get('text','')}")
            c = Counter(toks)
            self.tf.append(c)
            self.len.append(len(toks))
            self.df.update(c.keys())
        self.N = len(docs)
        self.avg = sum(self.len) / max(self.N, 1)
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5))
                    for t, n in self.df.items()}

    def search(self, q, topk=10):
        qt = tokenize(clean_query(q) or q)
        if not qt:
            return []
        scores = defaultdict(float)
        for t in set(qt):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, c in enumerate(self.tf):
                f = c.get(t)
                if not f:
                    continue
                scores[i] += idf * f * (K1 + 1) / (
                    f + K1 * (1 - B + B * self.len[i] / self.avg))
        top = sorted(scores.items(), key=lambda x: -x[1])[:topk]
        return [(self.docs[i], s) for i, s in top if s > 0]


def load_docs():
    cls = {r["id"]: r for r in json.loads((ROOT / "data" / "classified.json").read_text())}
    docs = []
    for line in (ROOT / "data" / "corpus.jsonl").read_text().split("\n"):
        if not line.strip():
            continue
        r = json.loads(line)
        c = cls.get(r["id"], {})
        docs.append({
            "id": r["id"], "title": r["title"], "text": r.get("text", ""),
            "author": r.get("author", ""), "category": c.get("category", ""),
            "url": r.get("url", ""), "type": r.get("type", ""),
        })
    return docs


if __name__ == "__main__":
    import sys
    docs = load_docs()
    idx = Index(docs)
    q = " ".join(sys.argv[1:]) or "Reddit 冷启动"
    print(f"索引 {idx.N} 篇 / {len(idx.df):,} 个 token\n查询：{q}\n" + "-" * 60)
    for d, s in idx.search(q, 8):
        print(f"{s:6.1f}  [{d['category']:<10}] {d['title'][:40]}")
