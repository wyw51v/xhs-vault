#!/usr/bin/env python3
"""生成单文件 HTML 看板：回看 / 画布 / 列表。自包含，无外部依赖。"""
import json, html, re
from collections import Counter
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _precond import need

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / "out" / "dashboard.html"


def likes(v):
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


def md_to_html(md):
    out, i, lines = [], 0, md.split("\n")
    def inline(t):
        t = html.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
        t = re.sub(r"\[\[(.+?)\]\]", r"<em>\1</em>", t)
        return t
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|") and i + 1 < len(lines) and \
           set(lines[i+1].replace("|", "").replace(" ", "")) <= set("-:"):
            head = [c.strip() for c in ln.strip("|").split("|")]
            i += 2
            body = []
            while i < len(lines) and lines[i].startswith("|"):
                body.append([c.strip() for c in lines[i].strip("|").split("|")]); i += 1
            out.append("<div class='tw'><table><thead><tr>" +
                       "".join(f"<th>{inline(c)}</th>" for c in head) +
                       "</tr></thead><tbody>" +
                       "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
                               for r in body) + "</tbody></table></div>")
            continue
        if re.match(r"^#{1,4} ", ln):
            n = len(ln) - len(ln.lstrip("#"))
            out.append(f"<h{n+1}>{inline(ln[n:].strip())}</h{n+1}>")
        elif ln.strip() == "---":
            out.append("<hr>")
        elif ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>"); i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "".join(out)


def main():
    need(ROOT, "class")
    cls = json.loads((ROOT / "data" / "classified.json").read_text())
    corpus = {}
    cp = ROOT / "data" / "corpus.jsonl"
    if cp.exists():
        for line in cp.read_text().split("\n"):
            if line.strip():
                r = json.loads(line)
                corpus[r["id"]] = r

    items = []
    for r in cls:
        c = corpus.get(r["id"], {})
        d = (c.get("text") or "").strip()
        items.append({"id": r["id"],
                      "t": r["title"], "u": r.get("user", ""), "c": r["category"],
                      "e": r["entities"], "v": r.get("type") == "video",
                      "l": likes(r.get("liked")), "url": r.get("url", ""),
                      "d": d[:400], "dl": len(d),
                      # 三个来源分开存，阅读面板里分别标注
                      "body": (c.get("desc") or "").strip(),
                      "srt": (c.get("subtitle_text") or "").strip(),
                      "ocr": (c.get("ocr_text") or "").strip(),
                      "tags": (c.get("tags") or [])[:10],
                      "time": c.get("time"),
                      "dur": int(c.get("video_duration") or 0) // 60000})
    items.sort(key=lambda x: -x["l"])

    cats = Counter(i["c"] for i in items)
    ents = Counter(e for i in items for e in i["e"])

    tree = json.loads((ROOT / "data" / "tree.json").read_text())
    md = ROOT / "out" / "收藏夹回看.md"
    review = md_to_html(md.read_text()) if md.exists() else ""

    subst = {
        "__DATA__":   json.dumps(items, ensure_ascii=False),
        "__CATS__":   json.dumps(cats.most_common(), ensure_ascii=False),
        "__ENTS__":   json.dumps(ents.most_common(40), ensure_ascii=False),
        "__TREE__":   json.dumps(tree, ensure_ascii=False),
        "__REVIEW__": review,
    }
    doc = TEMPLATE
    for k, v in subst.items():
        doc = doc.replace(k, v.replace("</", "<\\/") if k != "__REVIEW__" else v)
    OUT.write_text(doc)
    nc = sum(len(d["cats"]) for d in tree)
    ns = sum(len(c["subs"]) for d in tree for c in d["cats"])
    print(f"html -> {OUT}  ({OUT.stat().st_size//1024} KB, {len(items)} 条, "
          f"{len(tree)} 领域 / {nc} 分类 / {ns} 子簇)")


TEMPLATE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>小红书收藏夹</title><style>
:root{--bg:#fbfbfa;--card:#fff;--ink:#1a1a19;--dim:#6b6b68;--line:#e6e4e0;--accent:#c2410c;--chip:#f1efec;--grid:#eeece8}
@media(prefers-color-scheme:dark){:root{--bg:#16171a;--card:#1e2024;--ink:#e8e6e3;--dim:#9a9893;--line:#2e3136;--accent:#fb923c;--chip:#262a30;--grid:#212429}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:26px 20px 70px}
.wide{max-width:none;padding:26px 24px 24px}
h1{font-size:23px;margin:0 0 3px;letter-spacing:-.01em}
.sub{color:var(--dim);font-size:13.5px;margin-bottom:18px}
.tabs{display:flex;gap:3px;margin-bottom:16px;border-bottom:1px solid var(--line)}
.tab{padding:8px 17px;cursor:pointer;color:var(--dim);font-size:14px;border-bottom:2px solid transparent;margin-bottom:-1px}
.tab.on{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}
/* ---------- 回看 ---------- */
#viewR{max-width:760px;font-size:15px}
#viewR h2{font-size:21px;margin:34px 0 10px;letter-spacing:-.01em}
#viewR h3{font-size:16.5px;margin:26px 0 8px}
#viewR h4{font-size:15px;margin:20px 0 6px;color:var(--accent)}
#viewR p{margin:10px 0;line-height:1.75}
#viewR hr{border:0;border-top:1px solid var(--line);margin:30px 0}
#viewR code{background:var(--chip);padding:1px 5px;border-radius:4px;font-size:13px}
#viewR ul{padding-left:20px;line-height:1.75}
#viewR .tw{overflow-x:auto;margin:14px 0}
#viewR table{border-collapse:collapse;width:100%;font-size:13.5px}
#viewR th,#viewR td{border-bottom:1px solid var(--line);padding:7px 10px;text-align:left;white-space:nowrap}
#viewR th{color:var(--dim);font-weight:600;font-size:12.5px}
#viewR td:not(:first-child){text-align:right}
#viewR em{font-style:normal;color:var(--accent)}
/* ---------- 画布 ---------- */
#stage{position:relative;height:calc(100vh - 190px);min-height:520px;border:1px solid var(--line);
 border-radius:12px;overflow:hidden;background:var(--bg);
 background-image:radial-gradient(var(--grid) 1px,transparent 1px);background-size:22px 22px;cursor:grab}
#stage.drag{cursor:grabbing}
/* 连线和节点必须套在同一个变换容器里，只 transform 一次。
   分开各自 transform 会踩 transform-origin 不一致的坑：div 默认 0 0 而 SVG 默认 50% 50%，
   一缩放就分家。 */
#view{position:absolute;left:0;top:0;transform-origin:0 0;will-change:transform}
#pan{position:absolute;left:0;top:0}
#wires{position:absolute;left:0;top:0;overflow:visible;pointer-events:none}
#wires path{fill:none;stroke:var(--dim);stroke-width:1.6;opacity:.42}
#wires path.hot{stroke:var(--accent);stroke-width:2.2;opacity:.9}
.nd{position:absolute;background:var(--card);border:1px solid var(--line);border-radius:11px;
 padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.nd.root{border-color:var(--accent);border-width:1.5px}
.nd.dom{cursor:pointer;border-left:3px solid var(--dim)}
.nd.dom:hover{border-color:var(--accent);border-left-color:var(--accent)}
.nd.dom.open{border-color:var(--accent);border-left-color:var(--accent);border-left-width:5px}
.nd.dom .ttl{font-size:16.5px}
.nd.cat{cursor:pointer}
.nd.cat:hover{border-color:var(--accent)}
.nd.cat.open{border-color:var(--accent);border-left-width:4px}
.nd .ttl{font-weight:650;font-size:15px;margin-bottom:3px;display:flex;justify-content:space-between;gap:10px;align-items:baseline}
.nd .num{color:var(--accent);font-size:13px;font-weight:600;white-space:nowrap}
.nd .st{color:var(--dim);font-size:11.5px}
.nd.cat .sm{margin-top:7px;padding-top:7px;border-top:1px solid var(--line)}
.nd .sm{color:var(--dim);font-size:12.5px;line-height:1.65}
.nd .sm strong{color:var(--ink)}
.nd.sub{cursor:pointer}
.nd.sub:hover{border-color:var(--accent)}
.nd.sub .ttl{font-size:13.5px;font-weight:600;margin:0}
.nl{margin-top:8px;border-top:1px solid var(--line);padding-top:7px}
.nl a{display:block;color:var(--ink);text-decoration:none;font-size:12.5px;padding:3px 0;cursor:pointer;
 line-height:1.45;border-bottom:1px solid transparent}
.nl a:hover{color:var(--accent)}
.nl .au{color:var(--dim);font-size:11px}
.hint{color:var(--dim);font-size:12.5px;margin:0 0 10px}
.hint kbd{background:var(--chip);padding:1px 5px;border-radius:4px;font-size:11px;font-family:inherit}
.zoom{position:absolute;right:14px;bottom:14px;display:flex;gap:5px;z-index:5}
.zoom button{width:32px;height:32px;border:1px solid var(--line);background:var(--card);color:var(--ink);
 border-radius:8px;cursor:pointer;font-size:15px;line-height:1}
.zoom button:hover{border-color:var(--accent);color:var(--accent)}
/* ---------- 列表 ---------- */
.bar{position:sticky;top:0;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);z-index:10;margin-bottom:16px}
input[type=search]{width:100%;padding:10px 14px;border:1px solid var(--line);border-radius:9px;background:var(--card);color:var(--ink);font-size:15px;outline:none}
input[type=search]:focus{border-color:var(--accent)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.chip{padding:4px 11px;border-radius:20px;background:var(--chip);border:1px solid transparent;color:var(--dim);font-size:12.5px;cursor:pointer;white-space:nowrap}
.chip:hover{color:var(--ink)}
.chip.on{background:var(--accent);color:#fff}
.chip b{font-weight:600;opacity:.65;margin-left:4px}
.sec{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);margin:11px 0 5px}
.count{color:var(--dim);font-size:13px;margin:12px 0 10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:15px 16px;display:flex;flex-direction:column;gap:7px}
.card h3{margin:0;font-size:15.5px;line-height:1.4;font-weight:600}
.card h3 a{color:inherit;text-decoration:none}
.card h3 a:hover{color:var(--accent)}
.meta{font-size:12.5px;color:var(--dim);display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.badge{background:var(--chip);padding:1.5px 8px;border-radius:5px;font-size:11.5px}
.badge.v{color:var(--accent)}
.desc{font-size:13.5px;color:var(--dim);line-height:1.62;max-height:6.5em;overflow:hidden;white-space:pre-wrap}
.ents{display:flex;flex-wrap:wrap;gap:4px}
.ent{font-size:11px;padding:1px 7px;border-radius:4px;border:1px solid var(--line);color:var(--dim);cursor:pointer}
.ent:hover{border-color:var(--accent);color:var(--accent)}
.empty{color:var(--dim);padding:60px 0;text-align:center}
/* ---------- 搜索 ---------- */
#viewS{max-width:860px}
.qrow{display:flex;gap:8px;margin-bottom:8px}
#sq{flex:1;padding:12px 16px;border:1px solid var(--line);border-radius:10px;
 background:var(--card);color:var(--ink);font-size:15px;outline:none}
#sq:focus{border-color:var(--accent)}
#sask{padding:0 20px;border:0;border-radius:10px;background:var(--accent);color:#fff;
 font-size:14px;cursor:pointer;white-space:nowrap}
#sask:disabled{opacity:.5;cursor:default}
.bridge{font-size:12.5px;color:var(--dim);margin-bottom:18px;display:flex;align-items:center;gap:6px}
.dot{width:7px;height:7px;border-radius:50%;background:#999;display:inline-block}
.dot.on{background:#16a34a}
.ans{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
 border-radius:10px;padding:18px 20px;margin-bottom:20px;white-space:pre-wrap;line-height:1.8;font-size:14.5px}
.ans{white-space:normal}
.ans strong{color:var(--ink)}
.ans p{margin:9px 0}
.ans h3{font-size:15.5px;margin:20px 0 7px}
.ans h4{font-size:14px;margin:16px 0 6px;color:var(--accent)}
.ans ul{padding-left:20px;margin:8px 0}
.ans li{margin:3px 0}
.ans code{background:var(--chip);padding:1px 5px;border-radius:4px;font-size:12.5px}
.ans .tw{overflow-x:auto;margin:12px 0}
.ans table{border-collapse:collapse;width:100%;font-size:13px}
.ans th,.ans td{border-bottom:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top}
.ans th{color:var(--dim);font-weight:600;font-size:12px;white-space:nowrap}
.srcs{margin-bottom:24px}
.srcs h4{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--dim);margin:0 0 8px}
.hit{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:11px 14px;
 margin-bottom:7px;cursor:pointer}
.hit:hover{border-color:var(--accent)}
.hit .ht{font-size:14px;font-weight:600;margin-bottom:3px}
.hit .hm{font-size:12px;color:var(--dim)}
.hit .hs{float:right;color:var(--accent);font-size:12px;font-weight:600}
.hit .hx{font-size:12.5px;color:var(--dim);margin-top:5px;line-height:1.6}
.hit .go{color:var(--dim);text-decoration:none;font-size:11.5px;margin-left:7px;
 border-bottom:1px solid var(--line);white-space:nowrap}
.hit .go:hover{color:var(--accent);border-color:var(--accent)}
.ans a.nt{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--accent);cursor:pointer}
.ans a.nt:hover{color:var(--accent)}
.ans a.ex{color:var(--accent);text-decoration:none;font-size:11px;margin-left:2px;vertical-align:super}
.spin{color:var(--dim);font-size:13.5px;padding:16px 0}
.modes{display:flex;gap:5px;margin-left:auto}
.mode{padding:3px 10px;border-radius:14px;background:var(--chip);color:var(--dim);
 font-size:12px;cursor:pointer;border:1px solid transparent}
.mode.on{background:var(--accent);color:#fff}
.bridge code{background:var(--chip);padding:1px 6px;border-radius:4px;font-size:11.5px}
/* ---------- 阅读面板 ---------- */
#scrim{position:fixed;inset:0;background:rgba(0,0,0,.28);z-index:40;display:none}
#rd{position:fixed;top:0;right:0;bottom:0;width:min(720px,92vw);background:var(--card);
 border-left:1px solid var(--line);z-index:41;display:none;flex-direction:column;
 box-shadow:-8px 0 32px rgba(0,0,0,.14)}
#rd.on,#scrim.on{display:flex}
#rdh{padding:20px 26px 14px;border-bottom:1px solid var(--line);flex-shrink:0}
#rdh h2{margin:0 0 8px;font-size:19px;line-height:1.4;padding-right:34px}
#rdm{color:var(--dim);font-size:12.5px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
#rdb{overflow-y:auto;padding:20px 26px 60px;flex:1}
#rdb .sechd{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--accent);
 margin:24px 0 8px;font-weight:600;display:flex;align-items:center;gap:8px}
#rdb .sechd:first-child{margin-top:0}
#rdb .sechd::after{content:'';flex:1;height:1px;background:var(--line)}
#rdb .tx{white-space:pre-wrap;line-height:1.85;font-size:14.5px}
#rdb .tx.srt{line-height:1.9;color:var(--ink)}
#rdx{position:absolute;top:16px;right:20px;width:30px;height:30px;border:0;background:var(--chip);
 color:var(--dim);border-radius:8px;cursor:pointer;font-size:17px;line-height:1}
#rdx:hover{color:var(--ink)}
#rdgo{display:inline-block;margin-top:26px;padding:8px 16px;background:var(--chip);
 color:var(--ink);border-radius:8px;text-decoration:none;font-size:13px}
#rdgo:hover{background:var(--accent);color:#fff}
.card{cursor:pointer}
.card h3 a{cursor:pointer}
.rdtags{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
.rdtags span{font-size:11px;padding:1px 7px;border-radius:4px;background:var(--chip);color:var(--dim)}
</style></head><body><div class="wrap" id="page">
<h1>小红书收藏夹</h1><div class="sub" id="hdr"></div>
<div class="tabs"><span class="tab on" id="tabR">回看</span><span class="tab" id="tabS">搜索</span><span class="tab" id="tabC">画布</span><span class="tab" id="tabL">列表</span></div>

<div id="viewR">__REVIEW__</div>

<div id="viewS" style="display:none">
 <div class="qrow"><input id="sq" placeholder="想找什么？比如「怎么做海外冷启动」「ADHD 怎么专注」"><button id="sask">问 Claude</button></div>
 <div class="bridge"><span class="dot" id="sdot"></span><span id="sbr"></span>
  <span class="modes" id="smodes"><span class="mode on" data-m="deep">深度</span><span class="mode" data-m="fast">快速</span></span></div>
 <div id="sout"></div>
</div>

<div id="viewC" style="display:none">
 <p class="hint">点领域 → 分类 → 子簇 → 笔记，逐层展开读全文。空白处拖动或双指滑动可平移，捏合（或 <kbd>⌘</kbd>+滚轮）缩放。</p>
 <div id="stage"><div id="view"><svg id="wires"></svg><div id="pan"></div></div>
  <div class="zoom"><button id="zi">＋</button><button id="zo">－</button><button id="zf">⤢</button></div>
 </div>
</div>

<div id="viewL" style="display:none">
 <div class="bar"><input type="search" id="q" placeholder="搜索标题、作者、正文…">
  <div class="sec">分类</div><div class="chips" id="cats"></div>
  <div class="sec">实体</div><div class="chips" id="ents"></div>
  <div class="sec">其他</div><div class="chips" id="misc"></div></div>
 <div class="count" id="count"></div><div class="grid" id="grid"></div>
</div>
<div id="scrim"></div>
<div id="rd"><div id="rdh"><button id="rdx">✕</button><h2 id="rdt"></h2><div id="rdm"></div>
 <div class="rdtags" id="rdtg"></div></div><div id="rdb"></div></div>
</div><script>
const D=__DATA__, CATS=__CATS__, ENTS=__ENTS__, T=__TREE__;
const el=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
el('hdr').textContent=`${D.length} 条 · ${T.length} 领域 / `
 +`${T.reduce((a,d)=>a+d.cats.length,0)} 分类 / ${T.reduce((a,d)=>a+d.cats.reduce((b,c)=>b+c.subs.length,0),0)} 子簇 · `
 +`已提取正文 ${D.filter(x=>x.dl).length} 条 · 视频 ${D.filter(x=>x.v).length} 条`;

/* ================= 画布 ================= */
const openDom=new Set(), openCat=new Set(), openSub=new Set();
const X0=20, XD=360, XC=820, XS=1280, GAP=13;
let sc=.9, ox=0, oy=0, built=false, extent={w:900,h:900};
const byId=new Map(D.map(x=>[x.id,x]));
const bold=t=>t.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');

function layout(){
 const pan=el('pan'); pan.innerHTML='';
 const svg=el('wires'); svg.innerHTML='';
 const wires=[]; let y=0; const domCenters=[]; let deepest=1;

 T.forEach((dom,di)=>{
  const dOpen=openDom.has(dom.name), domY0=y, catCenters=[];
  if(dOpen){ deepest=Math.max(deepest,2);
   dom.cats.forEach((cat,ci)=>{
    const cKey=dom.name+'/'+cat.name, cOpen=openCat.has(cKey), catY0=y, subCenters=[];
    if(cOpen){ deepest=Math.max(deepest,3);
     cat.subs.forEach((sub,si)=>{
      const sKey=cKey+'/'+sub.name, sOpen=openSub.has(sKey);
      const d=document.createElement('div');
      d.className='nd sub'+(sOpen?' open':'');
      d.style.cssText=`left:${XS}px;width:370px`;
      d.innerHTML=`<div class="ttl"><span>${esc(sub.name)}</span><span class="num">${sub.n}</span></div>`
       +(sOpen?`<div class="nl">${sub.notes.map(n=>
          `<a data-k="${esc(n.id)}">${n.v?'🎬':'📄'} ${esc(n.t)}`
          +`<span class="au"> · ${esc(n.u)}${n.len?' · '+n.len+'字':''}</span></a>`).join('')}</div>`
         :`<div class="sm">${esc(sub.notes.slice(0,3).map(n=>n.t).join(' · ')).slice(0,88)}…</div>`);
      d.onclick=e=>{const a=e.target.closest('a');
        if(a){openRd(byId.get(a.dataset.k));return}
        sOpen?openSub.delete(sKey):openSub.add(sKey);layout()};
      pan.appendChild(d);
      const h=d.offsetHeight; d.style.top=y+'px';
      subCenters.push(y+h/2); y+=h+GAP;
     });
     y+=10;
    }
    const cBlk=cOpen?Math.max(y-catY0-GAP-10,68):68;
    const c=document.createElement('div');
    c.className='nd cat'+(cOpen?' open':'');
    c.style.cssText=`left:${XC}px;width:390px`;
    c.innerHTML=`<div class="ttl"><span>${esc(cat.name)}</span><span class="num">${cat.n}</span></div>`
     +`<div class="st">${cat.img} 图文 · ${cat.video} 视频 · ${cat.subs.length} 子簇</div>`
     +(cOpen&&cat.summary?`<div class="sm">${bold(cat.summary)}</div>`:'');
    c.onclick=()=>{if(cOpen){openCat.delete(cKey)}else{
      T.forEach(d2=>d2.cats.forEach(c2=>openCat.delete(d2.name+'/'+c2.name)));openCat.add(cKey)}
      layout();recentre('.nd.cat.open')};
    pan.appendChild(c);
    const ch=c.offsetHeight, cy=catY0+cBlk/2-ch/2;
    c.style.top=cy+'px';
    catCenters.push(cy+ch/2);
    subCenters.forEach(sy=>wires.push([XC+390,cy+ch/2,XS,sy,1]));
    y=Math.max(y,catY0+ch+GAP);
   });
   y+=12;
  }
  const dBlk=dOpen?Math.max(y-domY0-GAP-12,80):80;
  const d=document.createElement('div');
  d.className='nd dom'+(dOpen?' open':'');
  d.style.cssText=`left:${XD}px;width:420px`;
  d.innerHTML=`<div class="ttl"><span>${esc(dom.name)}</span><span class="num">${dom.n}</span></div>`
   +`<div class="st">${dom.cats.length} 分类 · ${dom.img} 图文 · ${dom.video} 视频</div>`
   +(dOpen&&dom.summary?`<div class="sm">${bold(dom.summary)}</div>`:'');
  d.onclick=()=>{if(dOpen){openDom.delete(dom.name)}else{openDom.clear();openDom.add(dom.name)}
    layout();recentre('.nd.dom.open')};
  pan.appendChild(d);
  const dh=d.offsetHeight, dy=domY0+dBlk/2-dh/2;
  d.style.top=dy+'px';
  domCenters.push(dy+dh/2);
  catCenters.forEach(cy=>wires.push([XD+420,dy+dh/2,XC,cy,1]));
  y=Math.max(y,domY0+dh+GAP*1.8);
 });

 const r=document.createElement('div');
 r.className='nd root'; r.style.cssText=`left:${X0}px;width:310px`;
 r.innerHTML=`<div class="ttl"><span>小红书收藏夹</span><span class="num">${D.length}</span></div>`
  +`<div class="st">${T.length} 个领域 · ${D.filter(x=>!x.v).length} 图文 · ${D.filter(x=>x.v).length} 视频</div>`
  +`<div class="sm">${D.reduce((a,x)=>a+x.dl,0).toLocaleString()} 字正文已提取。点右侧领域逐层展开。</div>`;
 pan.appendChild(r);
 const rh=r.offsetHeight, rcy=domCenters.length?Math.max(0,domCenters[0]-rh/2):0;
 r.style.top=rcy+'px';
 domCenters.forEach(dy=>wires.push([X0+310,rcy+rh/2,XD,dy,0]));

 extent={w:[X0+340,XD+450,XC+420,XS+400][deepest],h:y+40};
 svg.setAttribute('width',extent.w); svg.setAttribute('height',extent.h);
 wires.forEach(([x1,y1,x2,y2,hot])=>{
  const p=document.createElementNS('http://www.w3.org/2000/svg','path');
  const mx=(x1+x2)/2;
  p.setAttribute('d',`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`);
  if(hot)p.setAttribute('class','hot');
  svg.appendChild(p);
 });
 apply();
}
function recentre(sel){
 const st=el('stage').getBoundingClientRect(), n=document.querySelector(sel);
 sc=Math.max(.45,Math.min(1,(st.width-70)/extent.w));
 ox=Math.max(16,(st.width-extent.w*sc)/2);
 oy=n?Math.min(20,st.height/2-(n.offsetTop+n.offsetHeight/2)*sc):20;
 apply();
}
function fit(){
 // 按宽度适配，不按高度——高度撑满会缩到看不清字。竖向留给平移。
 const st=el('stage').getBoundingClientRect();
 sc=Math.max(.45,Math.min(1,(st.width-70)/extent.w));
 ox=Math.max(16,(st.width-extent.w*sc)/2); oy=20; apply();
}
function apply(){el('view').style.transform=`translate(${ox}px,${oy}px) scale(${sc})`}
(function(){const st=el('stage');let dg=null;
 st.addEventListener('mousedown',e=>{if(e.target.closest('.nd'))return;
  dg={x:e.clientX-ox,y:e.clientY-oy};st.classList.add('drag')});
 window.addEventListener('mousemove',e=>{if(!dg)return;ox=e.clientX-dg.x;oy=e.clientY-dg.y;apply()});
 window.addEventListener('mouseup',()=>{dg=null;st.classList.remove('drag')});
 // trackpad 双指滑动发的是普通 wheel，捏合发的是 ctrlKey=true 的 wheel。
 // 全绑到缩放会导致「想上下滚，结果在缩放」。按 Figma/Miro 的约定分开处理。
 st.addEventListener('wheel',e=>{e.preventDefault();
  if(e.ctrlKey||e.metaKey){
   const r=st.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
   const k=Math.exp(-e.deltaY*0.01), ns=Math.max(.25,Math.min(2.2,sc*k));
   ox=mx-(mx-ox)*ns/sc; oy=my-(my-oy)*ns/sc; sc=ns;
  }else{ ox-=e.deltaX; oy-=e.deltaY; }
  apply()},{passive:false});
 el('zi').onclick=()=>{sc=Math.min(2.2,sc*1.18);apply()};
 el('zo').onclick=()=>{sc=Math.max(.25,sc/1.18);apply()};
 el('zf').onclick=fit;
})();

/* ================= 列表 ================= */
let fc=null,fe=null,fm=null,q="";
function chips(box,arr,get,set){box.innerHTML='';arr.forEach(([n,c])=>{const b=document.createElement('span');
 b.className='chip';b.innerHTML=esc(n)+'<b>'+c+'</b>';b.dataset.n=n;
 b.onclick=()=>{set(get()===n?null:n);render()};box.appendChild(b)})}
chips(el('cats'),CATS,()=>fc,v=>{fc=v});
chips(el('ents'),ENTS,()=>fe,v=>{fe=v});
chips(el('misc'),[['视频',D.filter(x=>x.v).length],['图文',D.filter(x=>!x.v).length],
 ['长文 2000字+',D.filter(x=>x.dl>2000).length],['无正文',D.filter(x=>!x.dl).length]],()=>fm,v=>{fm=v});
el('q').oninput=e=>{q=e.target.value.toLowerCase();render()};
function pass(x){
 if(fc&&x.c!==fc)return false;
 if(fe&&!x.e.includes(fe))return false;
 if(fm==='视频'&&!x.v)return false;
 if(fm==='图文'&&x.v)return false;
 if(fm==='长文 2000字+'&&x.dl<=2000)return false;
 if(fm==='无正文'&&x.dl)return false;
 if(q&&!((x.t+' '+x.u+' '+x.d+' '+x.e.join(' ')).toLowerCase().includes(q)))return false;
 return true}
function render(){
 [['cats',fc],['ents',fe],['misc',fm]].forEach(([id,v])=>
  document.querySelectorAll('#'+id+' .chip').forEach(b=>b.classList.toggle('on',b.dataset.n===v)));
 const r=D.filter(pass);
 el('count').textContent=`显示 ${r.length} / ${D.length}`;
 el('grid').innerHTML=r.length?r.map(x=>`<div class="card">
  <h3>${esc(x.t)}</h3>
  <div class="meta"><span class="badge${x.v?' v':''}">${x.v?'🎬 视频'+(x.dur?' '+x.dur+'min':''):'📄 图文'}</span>
  <span class="badge">${esc(x.c)}</span><span>${esc(x.u)}</span>${x.l?'<span>♥ '+x.l+'</span>':''}</div>
  ${x.d?`<div class="desc">${esc(x.d)}</div>`:'<div class="desc" style="opacity:.5">（无正文）</div>'}
  ${x.e.length?`<div class="ents">${x.e.map(e=>`<span class="ent" data-e="${esc(e)}">${esc(e)}</span>`).join('')}</div>`:''}
  </div>`).join(''):'<div class="empty">没有匹配的收藏</div>';
 el('grid').querySelectorAll('.ent').forEach(s=>s.onclick=e=>{e.stopPropagation();fe=s.dataset.e;render();window.scrollTo(0,0)});
 el('grid').querySelectorAll('.card').forEach((c,i)=>c.onclick=()=>openRd(r[i]));
}

/* ================= 阅读面板 ================= */
function openRd(x){
 if(!x)return;
 el('rdt').textContent=x.t;
 el('rdm').innerHTML=`<span class="badge${x.v?' v':''}">${x.v?'🎬 视频'+(x.dur?' '+x.dur+' 分钟':''):'📄 图文'}</span>`
  +`<span class="badge">${esc(x.c)}</span><span>${esc(x.u)}</span>`
  +(x.l?`<span>♥ ${x.l}</span>`:'')+(x.dl?`<span>${x.dl.toLocaleString()} 字</span>`:'');
 el('rdtg').innerHTML=(x.e||[]).map(e=>`<span>${esc(e)}</span>`).join('');
 const P=[];
 if(x.body)P.push(['帖子正文',x.body,'']);
 if(x.ocr) P.push(['图片文字 · 本地 OCR',x.ocr,'']);
 if(x.srt) P.push(['视频字幕 · 平台原字幕',x.srt,'srt']);
 el('rdb').innerHTML=(P.length
   ?P.map(([h,t,c])=>`<div class="sechd">${h}</div><div class="tx ${c}">${esc(t)}</div>`).join('')
   :'<div class="empty">这条没有可提取的正文</div>')
  +`<a id="rdgo" href="${esc(x.url)}" target="_blank" rel="noopener">在小红书打开原帖 ↗</a>`;
 el('rd').classList.add('on'); el('scrim').classList.add('on');
 el('rdb').scrollTop=0;
}
function closeRd(){el('rd').classList.remove('on');el('scrim').classList.remove('on')}
el('rdx').onclick=closeRd; el('scrim').onclick=closeRd;
window.addEventListener('keydown',e=>{if(e.key==='Escape')closeRd()});

/* ================= 搜索 ================= */
// Claude 在回答里会写笔记标题。把这些标题变成链接：点标题开本地全文，
// 后面那个 ↗ 直达小红书原帖。
// 只在文本节点上替换 —— 字符串拼接会破坏 mdRender 生成的表格/列表标签。
const TITLES = D.filter(x=>x.t && x.t.length>=6)
                .map(x=>({t:x.t, id:x.id, url:x.url}))
                .sort((a,b)=>b.t.length-a.t.length);   // 长标题优先，避免被短标题截断
function linkifyTitles(root){
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{
  acceptNode:n=>n.parentElement.closest('a')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});
 const texts=[]; let n; while(n=walker.nextNode())texts.push(n);
 texts.forEach(node=>{
  let rest=node.nodeValue, frag=null, guard=0;
  while(guard++<40){
   let best=null,bi=-1;
   for(const T of TITLES){const i=rest.indexOf(T.t); if(i>=0&&(bi<0||i<bi)){bi=i;best=T;break}}
   if(!best)break;
   frag=frag||document.createDocumentFragment();
   if(bi>0)frag.appendChild(document.createTextNode(rest.slice(0,bi)));
   const a=document.createElement('a');
   a.className='nt'; a.textContent=best.t; a.dataset.id=best.id;
   frag.appendChild(a);
   const ex=document.createElement('a');
   ex.className='ex'; ex.href=best.url; ex.target='_blank'; ex.rel='noopener';
   ex.textContent='↗'; ex.title='在小红书打开原帖';
   frag.appendChild(ex);
   rest=rest.slice(bi+best.t.length);
  }
  if(frag){
   if(rest)frag.appendChild(document.createTextNode(rest));
   node.parentNode.replaceChild(frag,node);
  }
 });
 root.querySelectorAll('a.nt').forEach(a=>a.onclick=e=>{
  e.preventDefault(); openRd(byId.get(a.dataset.id));
 });
}

// Claude 返回的是 markdown。够用就好的渲染：标题 / 表格 / 列表 / 粗体 / 行内码。
function mdRender(md){
 const inl=t=>esc(t)
   .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
   .replace(/`(.+?)`/g,'<code>$1</code>');
 const L=String(md||'').split('\n'), out=[];
 let i=0;
 while(i<L.length){
  const ln=L[i];
  if(/^\|/.test(ln)&&i+1<L.length&&/^\|[\s|:-]+\|?\s*$/.test(L[i+1])){
   const cell=r=>r.replace(/^\||\|$/g,'').split('|').map(c=>c.trim());
   const head=cell(ln); i+=2; const body=[];
   while(i<L.length&&/^\|/.test(L[i])){body.push(cell(L[i]));i++}
   out.push('<div class="tw"><table><thead><tr>'+head.map(c=>`<th>${inl(c)}</th>`).join('')
    +'</tr></thead><tbody>'+body.map(r=>'<tr>'+r.map(c=>`<td>${inl(c)}</td>`).join('')+'</tr>').join('')
    +'</tbody></table></div>');
   continue;
  }
  const h=ln.match(/^(#{1,4})\s+(.*)$/);
  if(h){out.push(`<h${Math.min(4,h[1].length+1)}>${inl(h[2])}</h${Math.min(4,h[1].length+1)}>`);i++;continue}
  if(/^\s*[-*]\s+/.test(ln)){
   const it=[];
   while(i<L.length&&/^\s*[-*]\s+/.test(L[i])){it.push(`<li>${inl(L[i].replace(/^\s*[-*]\s+/,''))}</li>`);i++}
   out.push('<ul>'+it.join('')+'</ul>');continue;
  }
  if(ln.trim())out.push(`<p>${inl(ln)}</p>`);
  i++;
 }
 return out.join('');
}

let bridge=false;
let smode='deep';
document.querySelectorAll('#smodes .mode').forEach(b=>b.onclick=()=>{
 smode=b.dataset.m;
 document.querySelectorAll('#smodes .mode').forEach(x=>x.classList.toggle('on',x===b));
});
fetch('/api/health').then(r=>r.json()).then(d=>{bridge=true;
 el('sdot').classList.add('on');
 el('sbr').textContent=d.claude
  ? `本地服务已连接 · ${d.docs} 篇已索引 · 可以问 Claude`
  : `本地服务已连接 · ${d.docs} 篇已索引 · 但机器上找不到 claude 命令，只能关键词检索`;
 el('sask').disabled=!d.claude;
}).catch(()=>{
 el('sbr').innerHTML='未连接本地服务 —— 只能做关键词匹配。要启用 Claude 问答，'
  +'双击项目里的 <code>启动收藏夹.command</code>（或装一次 <code>安装开机自启.command</code>，'
  +'之后就不用管了）。';
 el('sask').disabled=true;
 el('smodes').style.display='none';
});

function esc2(s){return esc(s)}
function hitHTML(x,score,snippet){
 return `<div class="hit" data-id="${esc(x.id)}">
  ${score!==undefined?`<span class="hs">${score}</span>`:''}
  <div class="ht">${x.v?'🎬':'📄'} ${esc(x.t)}</div>
  <div class="hm">${esc(x.u)} · ${esc(x.c)}${x.dl?' · '+x.dl.toLocaleString()+'字':''}
   <a class="go" href="${esc(x.url)}" target="_blank" rel="noopener">原帖 ↗</a></div>
  ${snippet?`<div class="hx">${esc(snippet)}</div>`:''}</div>`;
}
function bindHits(){
 el('sout').querySelectorAll('.hit').forEach(h=>h.onclick=e=>{
  if(e.target.closest('a'))return;              // 点「原帖 ↗」不要同时开阅读面板
  openRd(byId.get(h.dataset.id));
 });
}
function snippetFor(x,q){
 const body=(x.body||'')+' '+(x.ocr||'')+' '+(x.srt||'');
 const k=q.split(/\s+/).filter(w=>w.length>1)[0]||q;
 const i=body.indexOf(k);
 return i<0?body.slice(0,110):body.slice(Math.max(0,i-40),i+110);
}
// 本地兜底：服务不在时用关键词计分，保证双击 HTML 也能搜
function localFind(q){
 const terms=q.toLowerCase().split(/[\s，。？！、]+/).filter(w=>w.length>1);
 if(!terms.length)return [];
 return D.map(x=>{
  const hay=(x.t+' '+x.u+' '+x.c+' '+(x.body||'')+(x.ocr||'')+(x.srt||'')).toLowerCase();
  let sc=0;
  terms.forEach(t=>{
   let i=0,n=0; while((i=hay.indexOf(t,i))>=0){n++;i+=t.length;if(n>20)break}
   if(n)sc+=n*(x.t.toLowerCase().includes(t)?6:1);
  });
  return [x,sc];
 }).filter(p=>p[1]>0).sort((a,b)=>b[1]-a[1]).slice(0,25);
}
let stimer=null;
el('sq').oninput=()=>{clearTimeout(stimer);stimer=setTimeout(runFind,220)};
el('sq').onkeydown=e=>{if(e.key==='Enter'&&!el('sask').disabled)runAsk()};
async function runFind(){
 const q=el('sq').value.trim();
 if(!q){el('sout').innerHTML='';return}
 let rows;
 if(bridge){
  try{
   const r=await fetch('/api/find?q='+encodeURIComponent(q)).then(r=>r.json());
   rows=r.hits.map(h=>[byId.get(h.id),h.score]).filter(p=>p[0]);
  }catch(e){rows=localFind(q)}
 }else rows=localFind(q);
 el('sout').innerHTML=rows.length
  ?`<div class="srcs"><h4>关键词命中 ${rows.length} 条</h4>`
   +rows.map(([x,sc])=>hitHTML(x,sc,snippetFor(x,q))).join('')+'</div>'
  :'<div class="empty">没有命中。换个说法，或点「问 Claude」让它理解你的意思。</div>';
 bindHits();
}
async function runAsk(){
 const q=el('sq').value.trim(); if(!q)return;
 el('sask').disabled=true; el('sask').textContent='思考中…';
 el('sout').innerHTML='<div class="spin">'
  +(smode==='deep'
    ? 'Claude 正在自己检索：多轮搜索 → 读出正文 → 交叉比对…（1~2 分钟）'
    : '正在把 BM25 筛出的 8 条交给 Claude 阅读…（约 15 秒）')
  +'</div>';
 try{
  const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({q,mode:smode})}).then(r=>r.json());
  el('sout').innerHTML=`<div class="ans">${mdRender(r.answer)}</div>`
   +(r.sources&&r.sources.length?`<div class="srcs"><h4>${r.mode==='deep'?'本地检索也命中了这些，可对照点开':'Claude 读了这 '+r.sources.length+' 条'}</h4>`
     +r.sources.map(s=>{const x=byId.get(s.id);
       return x?hitHTML(x,s.n,''):''}).join('')+'</div>':'');
  bindHits();
  const ansEl=document.querySelector('.ans');
  if(ansEl)linkifyTitles(ansEl);
 }catch(e){
  el('sout').innerHTML='<div class="empty">调用失败：'+esc(String(e))+'</div>';
 }
 el('sask').disabled=false; el('sask').textContent='问 Claude';
}
el('sask').onclick=runAsk;

/* ================= tabs ================= */
function showTab(w){
 el('viewR').style.display=w==='R'?'':'none';
 el('viewS').style.display=w==='S'?'':'none';
 el('tabS').classList.toggle('on',w==='S');
 if(w==='S')setTimeout(()=>el('sq').focus(),50);
 el('viewC').style.display=w==='C'?'':'none';
 el('viewL').style.display=w==='L'?'':'none';
 el('page').classList.toggle('wide',w==='C');
 el('tabR').classList.toggle('on',w==='R');
 el('tabC').classList.toggle('on',w==='C');
 el('tabL').classList.toggle('on',w==='L');
 if(w==='C'&&!built){layout();fit();built=true}
}
el('tabR').onclick=()=>showTab('R');
el('tabS').onclick=()=>showTab('S');
el('tabC').onclick=()=>showTab('C');
el('tabL').onclick=()=>showTab('L');
render();showTab('R');
</script></body></html>"""


if __name__ == "__main__":
    main()
