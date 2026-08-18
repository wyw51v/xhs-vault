// ==UserScript==
// @name         小红书收藏夹全量导出
// @namespace    xhs-kg
// @version      1.1
// @description  抓取小红书收藏夹全部笔记的 id / xsec_token / 标题，导出 JSON；顺带导出 cookies.json
// @author       xhs-kg
// @match        https://www.xiaohongshu.com/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function () {
  'use strict';

  // ---------- 状态 ----------
  const STORE = new Map();               // note_id -> record
  const META  = { pages: 0, hasMore: null, lastCode: null, lastMsg: '', endpoints: new Set() };
  const LSKEY = '__xhs_kg_export__';
  let running = false, scroller = null;

  // 恢复上次进度
  try {
    const old = JSON.parse(localStorage.getItem(LSKEY) || '[]');
    for (const r of old) if (r && r.id) STORE.set(r.id, r);
  } catch (e) {}

  const RE_ENDPOINT = /\/api\/sns\/web\/.*(collect|board|fav)/i;

  // ---------- 吸收响应 ----------
  function absorb(url, json) {
    try {
      if (!json || typeof json !== 'object') return;
      const d = json.data;
      if (json.code !== undefined && json.code !== 0 && json.code !== null) {
        META.lastCode = json.code;
        META.lastMsg  = json.msg || '';
      }
      if (!d) return;
      META.endpoints.add(url.split('?')[0].replace(/^https?:\/\/[^/]+/, ''));
      if ('has_more' in d) META.hasMore = d.has_more;
      const notes = d.notes || d.note_list || d.items || [];
      if (!Array.isArray(notes) || !notes.length) return;
      META.pages++;
      for (const n of notes) {
        const id = n.note_id || n.id || (n.note_card && n.note_card.note_id);
        if (!id) continue;
        const card = n.note_card || n;
        STORE.set(id, {
          id,
          token: n.xsec_token || card.xsec_token || '',
          title: card.display_title || card.title || '',
          type:  card.type || '',
          user:  (card.user && (card.user.nickname || card.user.nick_name)) || '',
          user_id: (card.user && (card.user.user_id || card.user.userId)) || '',
          liked: (card.interact_info && card.interact_info.liked_count) || '',
          cover: (card.cover && (card.cover.url_default || card.cover.url)) || '',
          src:   url.split('?')[0].replace(/^https?:\/\/[^/]+/, '')
        });
      }
      persist();
      render();
    } catch (e) { /* 静默 */ }
  }

  function persist() {
    try { localStorage.setItem(LSKEY, JSON.stringify([...STORE.values()])); } catch (e) {}
  }

  // ---------- Hook fetch ----------
  const _fetch = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const p = _fetch.apply(this, arguments);
    if (RE_ENDPOINT.test(url)) {
      p.then(r => { r.clone().json().then(j => absorb(url, j)).catch(() => {}); }).catch(() => {});
    }
    return p;
  };

  // ---------- Hook XHR ----------
  const _open = XMLHttpRequest.prototype.open;
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; return _open.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () {
    if (RE_ENDPOINT.test(this.__u || '')) {
      this.addEventListener('load', () => {
        try { absorb(this.__u, JSON.parse(this.responseText)); } catch (e) {}
      });
    }
    return _send.apply(this, arguments);
  };

  // ---------- 滚动 ----------
  function findScroller() {
    let best = document.scrollingElement || document.documentElement, bestGap = 0;
    const cands = document.querySelectorAll('body,div,main,section');
    for (let i = 0; i < cands.length; i++) {
      const el = cands[i];
      const gap = el.scrollHeight - el.clientHeight;
      if (gap > bestGap && el.clientHeight > 200) {
        const ov = getComputedStyle(el).overflowY;
        if (ov === 'auto' || ov === 'scroll' || el === document.body) { best = el; bestGap = gap; }
      }
    }
    return bestGap > 0 ? best : (document.scrollingElement || document.documentElement);
  }

  function step() {
    if (!scroller || scroller.scrollHeight - scroller.clientHeight <= 0) scroller = findScroller();
    const se = document.scrollingElement || document.documentElement;
    se.scrollTop = se.scrollHeight;
    if (scroller && scroller !== se) scroller.scrollTop = scroller.scrollHeight;
    window.scrollTo(0, document.body.scrollHeight);
  }

  const sleep = ms => new Promise(r => setTimeout(r, ms));

  async function run() {
    if (running) { running = false; return; }
    running = true; render();
    scroller = findScroller();
    let last = STORE.size, stall = 0;
    while (running && stall < 15) {
      step();
      await sleep(1000);
      if (STORE.size > last) { last = STORE.size; stall = 0; }
      else stall++;
      if (META.lastCode === -101 || META.lastCode === 300011) break;   // 掉线/风控，立即停
      if (META.hasMore === false && stall >= 4) break;                  // 真的到底了
      render(stall);
    }
    running = false; render();
  }

  // ---------- 导出 ----------
  function dl(name, text, mime) {
    const b = new Blob([text], { type: mime || 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(b); a.download = name;
    document.body.appendChild(a); a.click();
    setTimeout(() => { a.remove(); URL.revokeObjectURL(a.href); }, 2000);
  }

  function exportList() {
    const notes = [...STORE.values()].map(r => ({
      ...r,
      url: `https://www.xiaohongshu.com/explore/${r.id}?xsec_token=${r.token}&xsec_source=pc_user`
    }));
    dl('xhs-favorites-full.json', JSON.stringify({
      exported_at: new Date().toISOString(),
      count: notes.length,
      pages: META.pages,
      has_more_at_stop: META.hasMore,
      endpoints: [...META.endpoints],
      notes
    }, null, 2));
  }

  // cookies 导出格式与 chenxiachan/xhs-claude-skills 的 ~/cookies.json 保持一致
  function exportCookies() {
    const arr = document.cookie.split('; ').filter(Boolean).map(c => {
      const [name, ...rest] = c.split('=');
      const value = rest.join('=');
      return { name, value, domain: '.xiaohongshu.com', path: '/',
        expires: Date.now() / 1000 + 86400 * 30, size: name.length + value.length,
        httpOnly: false, secure: true, session: false, priority: 'Medium',
        sameParty: false, sourceScheme: 'Secure', sourcePort: 443 };
    });
    dl('cookies.json', JSON.stringify(arr, null, 2));
  }

  // ---------- UI ----------
  let ui;
  function render(stall) {
    if (!ui) return;
    const bad = META.lastCode === -101 || META.lastCode === 300011;
    ui.info.innerHTML =
      `<b style="font-size:20px">${STORE.size}</b> 条` +
      `<span style="opacity:.6"> · ${META.pages} 页</span><br>` +
      `<span style="opacity:.6">has_more: ${META.hasMore === null ? '—' : META.hasMore}` +
      (stall ? ` · 停滞 ${stall}/15` : '') + `</span>` +
      (bad ? `<br><span style="color:#ff6b6b">⚠ ${META.lastCode} ${META.lastMsg}<br>请重新登录后再跑</span>` : '');
    ui.go.textContent = running ? '⏸ 停止' : '▶ 开始滚动抓取';
    ui.go.style.background = running ? '#c92a2a' : '#1971c2';
  }

  function mount() {
    if (document.getElementById('xhs-kg-panel')) return;
    const p = document.createElement('div');
    p.id = 'xhs-kg-panel';
    p.style.cssText = 'position:fixed;top:80px;right:16px;z-index:2147483647;background:#1a1b1e;color:#e9ecef;' +
      'font:13px/1.5 -apple-system,sans-serif;padding:14px 16px;border-radius:10px;width:230px;' +
      'box-shadow:0 6px 24px rgba(0,0,0,.35)';
    p.innerHTML = '<div style="font-weight:600;margin-bottom:8px">收藏夹导出</div>' +
      '<div id="xhskg-info" style="margin-bottom:10px"></div>';
    const mk = (t, bg) => { const b = document.createElement('button');
      b.textContent = t; b.style.cssText = `display:block;width:100%;margin-top:6px;padding:7px;border:0;
      border-radius:6px;color:#fff;cursor:pointer;font-size:12px;background:${bg}`; p.appendChild(b); return b; };
    document.body.appendChild(p);
    ui = { info: p.querySelector('#xhskg-info') };
    ui.go = mk('▶ 开始滚动抓取', '#1971c2'); ui.go.onclick = run;
    ui.ex = mk('⬇ 导出清单 JSON', '#2f9e44'); ui.ex.onclick = exportList;
    ui.ck = mk('⬇ 导出 cookies.json', '#5f3dc4'); ui.ck.onclick = exportCookies;
    ui.rs = mk('✕ 清空已存进度', '#495057'); ui.rs.onclick = () => {
      if (confirm('清空本地已抓取的 ' + STORE.size + ' 条？')) { STORE.clear(); persist(); META.pages = 0; render(); } };
    render();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
  setInterval(mount, 3000);   // SPA 路由切换后重新挂载
})();
