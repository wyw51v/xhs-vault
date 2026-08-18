#!/usr/bin/env python3
"""收藏夹本地服务：静态看板 + Claude 问答桥接。

    python3 serve.py           # http://127.0.0.1:8899

浏览器不能直接调 Claude（没有 API key，也有 CORS 限制），
所以走本地桥接：HTML -> 这个服务 -> `claude -p` -> 回答。

检索用 BM25 先筛 8 条最相关的，只把这几条喂给 Claude。
不这么做的话每次问答都要送整个语料，又慢又贵。
"""
import json, subprocess, sys, threading, urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scraper"))
import search as S
from _precond import need

PORT, HOST = 8899, "127.0.0.1"
TOPK = 8              # fast 模式送给 Claude 的笔记条数
PER_NOTE = 1800       # fast 模式每条截断字数
MODEL = "claude-sonnet-5"
TIMEOUT_FAST, TIMEOUT_DEEP = 180, 420

need(ROOT, "corpus", "（先按 README 跑完抓取与处理，再启动服务）")
print("建索引…", file=sys.stderr)
DOCS = S.load_docs()
IDX = S.Index(DOCS)
print(f"索引就绪：{IDX.N} 篇 / {len(IDX.df):,} token", file=sys.stderr)

# deep 模式：不预先筛，告诉它库在哪，让它自己多轮检索、自己决定读哪几条。
# 实测 `claude -p` 有完整工具权限，能跑脚本读文件——预先塞 8 条等于浪费这个能力。
PROMPT_DEEP = """你在用户小红书收藏夹的本地知识库里检索。工作目录就是当前目录。

可用手段：
- `python3 scraper/search.py <关键词...>` — BM25 检索，返回最相关的标题 + 分类
- `data/corpus.jsonl` — 每行一条笔记的 JSON，字段 id/title/author/category/text
- 全库 {total} 条，约 {chars:,} 字正文（帖子正文 + 视频字幕 + 图片 OCR）

用户问题：{q}

要求：
- 先检索，再读出相关笔记正文；命中不理想就换关键词多搜几轮
- 只依据笔记内容回答，不要用你自己的知识补充事实
- 指出哪几条相关、各讲了什么；几条之间有矛盾或互补就说出来
- 收藏夹里没有就直说，不要硬凑
- 中文，用结构不要用长段落，不要用一级标题
"""

PROMPT_FAST = """你是用户小红书收藏夹的检索助手。下面是从 {total} 条收藏里检索出的最相关的 {n} 条笔记全文（已截断）。

用户的问题：{q}

要求：
- 只依据这些笔记回答，不要用你自己的知识补充事实
- 指出哪几条相关、各自讲了什么、能解决问题的哪一部分
- 如果这些笔记其实回答不了这个问题，直接说「收藏夹里没有」，不要硬凑
- 中文回答，简洁，用结构不要用长段落
- 引用笔记时写 [n] 标号

---
{notes}
"""


def run_claude(prompt, timeout):
    try:
        r = subprocess.run(["claude", "-p", "--model", MODEL],
                           input=prompt, capture_output=True, text=True,
                           timeout=timeout, cwd=str(ROOT))
    except FileNotFoundError:
        return None, ("找不到 claude 命令。装了 Claude Code 才能用问答；"
                      "关键词检索不受影响。")
    except subprocess.TimeoutExpired:
        return None, f"Claude 超时（>{timeout}s）。换个更具体的问法，或用快速模式。"
    if r.returncode != 0:
        return None, f"claude 调用失败：{(r.stderr or '')[:300]}"
    return r.stdout.strip(), None


def ask_deep(q):
    """让 Claude 自己检索。慢，但能多轮搜索、交叉比对。"""
    chars = sum(len(d.get("text") or "") for d in DOCS)
    out, err = run_claude(PROMPT_DEEP.format(total=IDX.N, chars=chars, q=q), TIMEOUT_DEEP)
    # 同时给出本地 BM25 命中，方便对照点开
    hits = IDX.search(q, 10)
    sources = [{"n": i, "id": d["id"], "title": d["title"], "author": d["author"],
                "category": d["category"], "url": d["url"], "score": round(sc, 1)}
               for i, (d, sc) in enumerate(hits, 1)]
    return {"answer": err or out, "sources": sources, "mode": "deep"}


def ask_fast(q):
    hits = IDX.search(q, TOPK)
    if not hits:
        return {"answer": "本地检索没有命中任何笔记。换个说法试试？", "sources": []}
    blocks, sources = [], []
    for i, (d, sc) in enumerate(hits, 1):
        body = (d["text"] or "").strip()[:PER_NOTE]
        blocks.append(f"[{i}] 《{d['title']}》 — {d['author']}（{d['category']}）\n{body}")
        sources.append({"n": i, "id": d["id"], "title": d["title"],
                        "author": d["author"], "category": d["category"],
                        "url": d["url"], "score": round(sc, 1)})
    prompt = PROMPT_FAST.format(total=IDX.N, n=len(hits), q=q,
                                notes="\n\n---\n\n".join(blocks))
    out, err = run_claude(prompt, TIMEOUT_FAST)
    return {"answer": err or out, "sources": sources, "mode": "fast"}


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "out"), **kw)

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/find"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q", [""])[0]
            hits = IDX.search(q, 30)
            return self._json({"hits": [{"id": d["id"], "title": d["title"],
                                         "score": round(s, 1)} for d, s in hits]})
        if self.path == "/api/health":
            import shutil
            return self._json({"ok": True, "docs": IDX.N,
                               "claude": bool(shutil.which("claude"))})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/ask":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            q = body.get("q", "").strip()
            mode = body.get("mode", "deep")
        except Exception:
            return self._json({"error": "bad json"}, 400)
        if not q:
            return self._json({"error": "empty query"}, 400)
        print(f"[ask/{mode}] {q}", file=sys.stderr)
        return self._json(ask_deep(q) if mode == "deep" else ask_fast(q))

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer((HOST, PORT), H)
    print(f"看板  http://{HOST}:{PORT}/dashboard.html", file=sys.stderr)
    print(f"问答  POST /api/ask  {{'q':'...', 'mode':'deep'|'fast'}}   模型 {MODEL}",
          file=sys.stderr)
    print("按 Ctrl-C 退出", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
