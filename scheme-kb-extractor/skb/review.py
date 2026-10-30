"""Builds out/review.html: the console a researcher uses to check the AI draft.

Three tabs:
  Review       every field next to its exact quote and location; approve, correct,
               or pick a side in a conflict. Nothing is publishable until every
               field has a human decision. A timer records how long checking took.
  Accuracy     the evaluation: readiness checks, accuracy by document type and field.
  How it works the pipeline and the rules, for people outside the team.

Decisions export as JSON; `python -m skb import-decisions` turns them into test answers.
"""
from __future__ import annotations

import json
from pathlib import Path

from .schema import HIGH_STAKES

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scheme Review Console</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#f6f7f9;--surface:#ffffff;--surface-2:#f9fafb;--ink:#0f172a;--ink-2:#334155;--muted:#64748b;--line:#e6e8ec;--line-2:#eef0f3;
--accent:#4338ca;--accent-ink:#ffffff;--accent-soft:#eef2ff;--ok:#047857;--ok-soft:#ecfdf5;--bad:#b91c1c;--bad-soft:#fef2f2;
--warn:#b45309;--warn-soft:#fffbeb;--idle:#475569;--idle-soft:#f1f5f9;--mark:#fde68a;--shadow:0 1px 2px rgba(15,23,42,.04),0 4px 16px rgba(15,23,42,.05);
--radius:14px;--font:"Inter","Noto Sans Devanagari",system-ui,"Segoe UI","Nirmala UI",sans-serif}
:root[data-theme="dark"]{--bg:#0b0d12;--surface:#12151c;--surface-2:#161a22;--ink:#e8eaf0;--ink-2:#c3c8d4;--muted:#8a93a6;--line:#232835;--line-2:#1c212b;
--accent:#818cf8;--accent-ink:#0b0d12;--accent-soft:#1e1b4b;--ok:#34d399;--ok-soft:#0d2a20;--bad:#f87171;--bad-soft:#2b1214;
--warn:#fbbf24;--warn-soft:#2a2010;--idle:#94a3b8;--idle-soft:#1a1f29;--mark:#854d0e;--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.25)}
*{box-sizing:border-box}html,body{margin:0}body{background:var(--bg);color:var(--ink);font:14px/1.55 var(--font);-webkit-font-smoothing:antialiased}
button,input{font:inherit;color:inherit}a{color:var(--accent)}
/* top bar */
.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--surface) 88%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.top-in{display:flex;align-items:center;gap:20px;padding:12px 28px;max-width:1480px;margin:0 auto}
.brand{display:flex;align-items:center;gap:12px;min-width:0}.logo{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#4338ca,#7c3aed);display:grid;place-items:center;color:#fff;flex:none}
.brand b{display:block;font-size:15px;letter-spacing:-.01em}.brand small{color:var(--muted);font-size:12px}
.tabs{display:flex;gap:4px;background:var(--surface-2);border:1px solid var(--line);border-radius:10px;padding:3px;margin-left:12px}
.tab{border:0;background:transparent;padding:6px 14px;border-radius:8px;cursor:pointer;color:var(--muted);font-weight:500}
.tab.on{background:var(--surface);color:var(--ink);box-shadow:var(--shadow)}
.sp{flex:1}.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:4px 10px;border-radius:999px;border:1px solid var(--line);background:var(--surface-2);color:var(--ink-2);white-space:nowrap}
.dot{width:7px;height:7px;border-radius:50%;background:var(--ok)}
.btn{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);background:var(--surface);border-radius:9px;padding:7px 13px;cursor:pointer;font-weight:500;white-space:nowrap}
.btn:hover{border-color:color-mix(in srgb,var(--accent) 35%,var(--line))}.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.btn.ok{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 35%,var(--line))}.btn.ghost{border-color:transparent;background:transparent;color:var(--muted)}
.icon-btn{width:36px;height:36px;padding:0;justify-content:center}
/* layout */
.page{max-width:1480px;margin:0 auto;padding:24px 28px 60px}.view{display:none}.view.on{display:block}
.grid{display:grid;grid-template-columns:300px minmax(0,1fr);gap:24px;align-items:start}
.side{position:sticky;top:84px}.side h4,.sec-h{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:0 0 10px;font-weight:600}
.sc{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:10px;cursor:pointer;transition:border-color .15s,box-shadow .15s}
.sc:hover{border-color:color-mix(in srgb,var(--accent) 30%,var(--line))}.sc.on{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.sc .t{font-weight:600;font-size:13.5px;line-height:1.35;margin:2px 0 8px}.sc .ref{font-size:11.5px;color:var(--muted);display:flex;justify-content:space-between}
.prog{height:5px;border-radius:3px;background:var(--line-2);overflow:hidden}.prog i{display:block;height:100%;background:var(--accent);border-radius:3px;transition:width .3s}
.mini{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
.tag{font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--idle-soft);color:var(--idle);white-space:nowrap}
.tag.bad{background:var(--bad-soft);color:var(--bad)}.tag.ok{background:var(--ok-soft);color:var(--ok)}.tag.warn{background:var(--warn-soft);color:var(--warn)}.tag.acc{background:var(--accent-soft);color:var(--accent)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
.hero{padding:22px 24px;display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap}.hero .eyebrow{font-size:12px;color:var(--muted);font-weight:500;display:flex;gap:8px;align-items:center}
.hero h1{font-size:22px;letter-spacing:-.02em;margin:6px 0 4px;line-height:1.3}.hero .dept{color:var(--ink-2)}
.timer{margin-left:auto;text-align:right}.timer b{font-size:20px;font-variant-numeric:tabular-nums;display:block}.timer small{color:var(--muted);font-size:12px}
.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:16px 0}
.kpi{padding:14px 16px}.kpi small{color:var(--muted);font-size:12px;font-weight:500}.kpi b{display:block;font-size:24px;letter-spacing:-.02em;margin-top:2px;font-variant-numeric:tabular-nums}
.kpi.bad b{color:var(--bad)}.kpi.ok b{color:var(--ok)}
.srcs{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-bottom:16px}
.src{padding:14px 16px;display:flex;gap:12px;align-items:flex-start}.src .ic{width:36px;height:36px;border-radius:10px;background:var(--accent-soft);color:var(--accent);display:grid;place-items:center;flex:none}
.src b{display:block;font-size:13.5px}.src small{color:var(--muted);font-size:12px;display:block}.src a{font-size:12.5px;font-weight:500;text-decoration:none}
.alert{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border-radius:12px;margin-bottom:10px;font-size:13.5px}
.alert.warn{background:var(--warn-soft);color:var(--warn)}.alert.bad{background:var(--bad-soft);color:var(--bad)}.alert.ok{background:var(--ok-soft);color:var(--ok)}.alert svg{flex:none;margin-top:2px}
.bar-row{display:flex;align-items:center;gap:12px;margin:18px 0 12px;flex-wrap:wrap}
.seg{display:flex;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:3px;gap:2px;flex-wrap:wrap}
.seg button{border:0;background:transparent;padding:5px 12px;border-radius:7px;cursor:pointer;color:var(--muted);font-size:13px;font-weight:500}
.seg button.on{background:var(--accent-soft);color:var(--accent)}.seg .n{opacity:.7;margin-left:4px}
.chk{display:flex;gap:8px;align-items:center;color:var(--muted);font-size:13px;cursor:pointer}
/* field cards */
.f{padding:18px 20px;margin-bottom:12px;transition:opacity .2s}.f.done{opacity:.66}.f.done:hover{opacity:1}
.f-h{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.f-h .nm{font-weight:600;font-size:15px}
.st{font-size:11.5px;font-weight:600;padding:3px 10px;border-radius:999px;display:inline-flex;gap:6px;align-items:center}
.st.found{background:var(--ok-soft);color:var(--ok)}.st.conflict{background:var(--bad-soft);color:var(--bad)}.st.not_found{background:var(--idle-soft);color:var(--idle)}
.conf{display:flex;align-items:center;gap:8px;margin-left:auto;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.meter{width:84px;height:6px;border-radius:3px;background:var(--line-2);overflow:hidden}.meter i{display:block;height:100%;border-radius:3px}
.val{font-size:16px;font-weight:500;margin:12px 0 6px;line-height:1.5}.val ul{margin:0;padding-left:20px;font-weight:400;font-size:14.5px}.val ul li{margin:2px 0}
.val .empty{color:var(--muted);font-weight:400;font-style:italic}
.cite{border-left:3px solid var(--accent);background:var(--surface-2);border-radius:0 10px 10px 0;padding:9px 12px;margin:8px 0}
.cite q{display:block;color:var(--ink-2);quotes:"“" "”"}.cite .m{font-size:11.5px;color:var(--muted);margin-top:4px;display:flex;gap:10px;flex-wrap:wrap}
mark{background:var(--mark);color:inherit;border-radius:3px;padding:0 2px}
.note{display:flex;gap:8px;font-size:13px;color:var(--muted);margin-top:10px;padding-top:10px;border-top:1px dashed var(--line)}.note svg{flex:none;margin-top:3px}
.cmp{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-top:12px}
.side-c{border:1px solid var(--line);border-radius:12px;padding:14px;background:var(--surface-2);display:flex;flex-direction:column}
.side-c .val{margin-top:6px}.side-c .btn{margin-top:auto;align-self:flex-start}.side-c .hd{display:flex;gap:6px;flex-wrap:wrap}
.acts{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap;align-items:center}
.acts input{flex:1;min-width:220px;padding:7px 11px;border:1px solid var(--line);border-radius:9px;background:var(--surface-2);outline:none}
.acts input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.decided{display:inline-flex;gap:6px;align-items:center;color:var(--ok);font-weight:600;font-size:12.5px}
/* accuracy + method */
.verdict{padding:22px 24px;display:flex;gap:18px;align-items:center;margin-bottom:16px}.verdict .big{width:52px;height:52px;border-radius:14px;display:grid;place-items:center;flex:none}
.verdict h2{margin:0;font-size:20px;letter-spacing:-.02em}.verdict p{margin:4px 0 0;color:var(--muted)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.pad{padding:18px 20px}
table{width:100%;border-collapse:collapse;font-size:13.5px}th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:10px;border-bottom:1px solid var(--line-2);vertical-align:middle}tr:last-child td{border-bottom:0}
.hbar{height:8px;border-radius:4px;background:var(--line-2);overflow:hidden;min-width:80px}.hbar i{display:block;height:100%;background:var(--accent);border-radius:4px}
.steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.step{padding:18px}.step .no{width:28px;height:28px;border-radius:8px;background:var(--accent-soft);color:var(--accent);display:grid;place-items:center;font-weight:700;font-size:13px}
.step b{display:block;margin:10px 0 4px}.step p{margin:0;color:var(--muted);font-size:13.5px}.step code{font-size:12px;color:var(--accent)}
.rules{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:16px 0}.rule{padding:18px 20px;border-left:4px solid var(--accent)}.rule b{display:block;margin-bottom:4px}.rule p{margin:0;color:var(--muted)}
.lead{color:var(--muted);max-width:760px;margin:4px 0 18px}h2.h{font-size:20px;letter-spacing:-.02em;margin:0}
.empty-state{padding:40px;text-align:center;color:var(--muted)}
@media (max-width:1100px){.kpis{grid-template-columns:repeat(3,1fr)}.steps{grid-template-columns:1fr 1fr}}
@media (max-width:860px){.grid,.two,.rules{grid-template-columns:1fr}.side{position:static}.top-in{flex-wrap:wrap;padding:10px 16px}.tabs{margin-left:0;order:3;width:100%}
.page{padding:16px}.kpis{grid-template-columns:repeat(2,1fr)}.steps{grid-template-columns:1fr}.timer{margin-left:0;text-align:left}.conf{margin-left:0}}
</style></head><body>
<header class="top"><div class="top-in">
  <div class="brand"><div class="logo"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z"/><path d="M8.5 12l2.5 2.5 4.5-5"/></svg></div>
    <div><b>Scheme Knowledge Base</b><small>Draft review console</small></div></div>
  <nav class="tabs"><button class="tab on" data-v="review">Review</button><button class="tab" data-v="accuracy">Accuracy</button><button class="tab" data-v="method">How it works</button></nav>
  <span class="sp"></span>
  <span class="pill" id="engine"><span class="dot"></span></span>
  <button class="btn icon-btn" id="theme" title="Switch theme"></button>
  <button class="btn primary" id="export"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>Export decisions</button>
</div></header>
<div class="page">
  <section class="view on" id="v-review"><div class="grid"><aside class="side"><h4>Schemes in this batch</h4><div id="nav"></div></aside><main id="main"></main></div></section>
  <section class="view" id="v-accuracy"></section>
  <section class="view" id="v-method"></section>
</div>
<script>
const DATA = __DATA__;
const HIGH = new Set(__HIGH__);
const LABEL = {scheme_name:"Scheme name",department:"Department",benefit_type:"Benefit type",benefit_amount:"Benefit amount",
 benefit_frequency:"Benefit frequency",eligibility:"Eligibility",documents_required:"Documents required",how_to_apply:"How to apply",
 deadline:"Deadline",official_link:"Official link"};
const STATUS = {found:"Found",conflict:"Conflict",not_found:"Not found"};
const I = {
  info:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>',
  warn:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17h.01"/></svg>',
  lock:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>',
  check:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  x:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  doc:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/></svg>',
  scan:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M7 12h10"/></svg>',
  web:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18"/></svg>',
  list:'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01"/></svg>',
  sun:'<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  moon:'<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>'
};
const SRC_ICON = {"Text PDF":I.doc,"Scanned PDF":I.scan,"Web page":I.web,"Press note":I.doc,"MyScheme listing":I.list};

const store = {get(k, d){try{return JSON.parse(localStorage.getItem(k)) ?? d}catch(e){return d}}, set(k, v){try{localStorage.setItem(k, JSON.stringify(v))}catch(e){}}};
const KEY = "skb-review-" + DATA.mode;
let decisions = store.get(KEY, {}), timers = store.get(KEY + "-timers", {});
let current = Object.keys(DATA.records)[0], filter = "all";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const key = (s, f) => s + "::" + f;
const pct = v => v == null ? "n/a" : Math.round(v * 100) + "%";
const confColor = c => c >= .8 ? "var(--ok)" : c >= .5 ? "var(--warn)" : "var(--bad)";
const meta = s => DATA.meta.schemes[s] || {sources: [], warnings: []};
const srcOf = ref => Object.values(DATA.meta.schemes).flatMap(m => m.sources).find(x => x.source_ref === ref.split(", ")[0]) || {};

function schemeTitle(s) {
  const r = DATA.records[s].find(x => x.field === "scheme_name");
  return r.value || (r.candidates[0] && r.candidates[0].value) || s;
}
function fmt(f, v) {
  if (v == null) return '<span class="empty">Left empty</span>';
  if (Array.isArray(v)) return "<ul>" + v.map(x => "<li>" + esc(x) + "</li>").join("") + "</ul>";
  if (f === "benefit_amount") return "₹" + Number(v).toLocaleString("en-IN");
  if (f === "benefit_frequency") return esc(String(v).replace("_", " ").replace(/^./, c => c.toUpperCase()));
  if (f === "deadline" && /^\d{4}-\d{2}-\d{2}$/.test(v)) return new Date(v + "T00:00").toLocaleDateString("en-IN", {day: "numeric", month: "long", year: "numeric"});
  if (f === "official_link") return `<a href="${esc(v)}" target="_blank" rel="noopener">${esc(v)}</a>`;
  return esc(v);
}
const DEV = "०१२३४५६७८९";
const toAscii = s => s.replace(/[०-९]/g, d => DEV.indexOf(d));
function highlight(f, quote, value) {
  let h = esc(quote);
  if (f === "benefit_amount" && value != null) {
    return h.replace(/[\d०-९][\d०-९,]*/g, m => Number(toAscii(m).replace(/,/g, "")) === Number(value) ? "<mark>" + m + "</mark>" : m);
  }
  if (typeof value === "string" && value.length > 2 && quote.includes(value)) return h.replace(esc(value), "<mark>" + esc(value) + "</mark>");
  return h;
}
const cite = (f, e, v) => `<div class="cite"><q>${highlight(f, e.quote, v)}</q><div class="m"><span>${esc(e.location)}</span><span>${esc(e.source_ref)}</span><span>${esc(e.source_link)}</span><span>Captured ${esc(e.captured_at)}</span></div></div>`;

function counts(s) {
  const recs = DATA.records[s];
  return {found: recs.filter(r => r.status === "found").length, conflict: recs.filter(r => r.status === "conflict").length,
    empty: recs.filter(r => r.status === "not_found").length, done: recs.filter(r => decisions[key(s, r.field)]).length, total: recs.length,
    avg: recs.filter(r => r.status === "found").reduce((a, r) => a + r.confidence, 0) / Math.max(1, recs.filter(r => r.status === "found").length)};
}
function needsAttention(r) { return r.status !== "found" || r.confidence < .6; }

function renderNav() {
  document.getElementById("nav").innerHTML = Object.keys(DATA.records).map(s => {
    const c = counts(s), m = meta(s);
    return `<div class="sc ${s === current ? "on" : ""}" data-s="${s}"><div class="ref"><span>${s} · ${esc(m.doc_type || "")}</span><span>${c.done}/${c.total}</span></div>
      <div class="t">${esc(schemeTitle(s))}</div><div class="prog"><i style="width:${c.done / c.total * 100}%"></i></div>
      <div class="mini">${c.conflict ? `<span class="tag bad">${c.conflict} conflict</span>` : ""}${c.empty ? `<span class="tag">${c.empty} empty</span>` : ""}
      ${m.warnings.length ? `<span class="tag warn">${m.warnings.length} warning</span>` : ""}${c.done === c.total ? '<span class="tag ok">Reviewed</span>' : ""}</div></div>`;
  }).join("");
  document.querySelectorAll(".sc").forEach(el => el.onclick = () => { current = el.dataset.s; filter = "all"; renderReview(); window.scrollTo({top: 0}); });
}

function startTimer(s) {
  if (!timers[s]) { timers[s] = {start: Date.now(), end: null}; store.set(KEY + "-timers", timers); }
}
function elapsed(s) {
  const t = timers[s]; if (!t) return "0:00";
  const sec = Math.round(((t.end || Date.now()) - t.start) / 1000);
  return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
}

function fieldCard(r) {
  const d = decisions[key(current, r.field)];
  let h = `<article class="card f ${d ? "done" : ""}"><div class="f-h"><span class="nm">${LABEL[r.field]}</span>
    <span class="st ${r.status}">${STATUS[r.status]}</span>${HIGH.has(r.field) ? '<span class="tag acc">High stakes</span>' : ""}
    ${d ? `<span class="decided">${I.check} ${esc(d.decision)}</span>` : ""}
    <span class="conf">Confidence <span class="meter"><i style="width:${Math.round(r.confidence * 100)}%;background:${confColor(r.confidence)}"></i></span>${r.confidence.toFixed(2)}</span></div>`;
  if (r.status === "conflict") {
    const newest = r.candidates.reduce((a, c) => (srcOf(c.source_ref).published_on || "") > (srcOf(a.source_ref).published_on || "") ? c : a);
    h += `<div class="cmp">` + r.candidates.map((c, i) => {
      const s = srcOf(c.source_ref);
      return `<div class="side-c"><div class="hd"><span class="tag ${s.authority === "primary" ? "acc" : ""}">${s.authority === "primary" ? "Official source" : "MyScheme catalogue"}</span>
        <span class="tag">Published ${esc(s.published_on)}</span>${c === newest ? '<span class="tag ok">Newest</span>' : ""}</div>
        <div class="val">${fmt(r.field, c.value)}</div>${c.evidence.map(e => cite(r.field, e, c.value)).join("")}
        <button class="btn" data-a="pick" data-f="${r.field}" data-i="${i}">Use this value</button></div>`;
    }).join("") + `</div>`;
  } else {
    h += `<div class="val">${fmt(r.field, r.value)}</div>` + r.evidence.map(e => cite(r.field, e, r.value)).join("");
    if (r.status === "not_found" && r.candidates.length) h += `<div class="cite" style="border-color:var(--warn)"><span class="tag warn">Unverified hint</span> <span class="m">${fmt(r.field, r.candidates[0].value)} from ${esc(r.candidates[0].source_ref)}</span></div>`;
  }
  if (r.note) h += `<div class="note">${I.info}<span>${esc(r.note)}</span></div>`;
  h += `<div class="acts">${r.status === "found" ? `<button class="btn ok" data-a="approve" data-f="${r.field}">${I.check} Approve</button>` : ""}
    ${r.status === "not_found" ? `<button class="btn" data-a="confirm_empty" data-f="${r.field}">Confirm empty</button>` : ""}
    <input placeholder="Type the correct value (use ; between list items)" data-in="${r.field}">
    <button class="btn" data-a="edit" data-f="${r.field}">Save correction</button>
    ${d ? `<button class="btn ghost" data-a="undo" data-f="${r.field}">Undo</button>` : ""}</div></article>`;
  return h;
}

function renderReview() {
  startTimer(current);
  renderNav();
  const c = counts(current), m = meta(current), recs = DATA.records[current];
  const dept = recs.find(r => r.field === "department");
  const open = c.total - c.done;
  let h = `<div class="card hero"><div><div class="eyebrow"><span>${current}</span><span>·</span><span>${esc(m.doc_type || "")}</span></div>
    <h1>${esc(schemeTitle(current))}</h1><div class="dept">${esc(dept.value || (dept.candidates[0] && dept.candidates[0].value) || "")}</div></div>
    <div class="timer"><small>Review time</small><b id="clock">${elapsed(current)}</b><small>${timers[current] && timers[current].end ? "finished" : "running"}</small></div></div>`;
  h += `<div class="kpis"><div class="card kpi ok"><small>Found</small><b>${c.found}</b></div><div class="card kpi ${c.conflict ? "bad" : ""}"><small>Conflicts</small><b>${c.conflict}</b></div>
    <div class="card kpi"><small>Left empty</small><b>${c.empty}</b></div><div class="card kpi"><small>Avg confidence (found)</small><b>${c.found ? c.avg.toFixed(2) : "–"}</b></div>
    <div class="card kpi"><small>Decided by reviewer</small><b>${c.done}<span style="font-size:15px;color:var(--muted)"> / ${c.total}</span></b></div></div>`;
  h += `<div class="sec-h">Sources</div><div class="srcs">` + m.sources.map(s => `<div class="card src"><div class="ic">${SRC_ICON[s.doc_type] || I.doc}</div><div>
    <b>${esc(s.title)}</b><small>${s.authority === "primary" ? "Official source" : "MyScheme catalogue"} · ${esc(s.language.toUpperCase())} · ${esc(s.doc_type)}</small>
    <small>Published ${esc(s.published_on)} · Captured ${esc(s.captured_at)}</small><a href="../data/${esc(s.path)}" target="_blank">Open document →</a></div></div>`).join("") + `</div>`;
  h += m.warnings.map(w => `<div class="alert warn">${I.warn}<span>${esc(w)}</span></div>`).join("");
  h += open ? `<div class="alert bad">${I.lock}<span><b>Not publishable.</b> ${open} field${open > 1 ? "s" : ""} still need a reviewer's decision. Nothing reaches agents or citizens until every field is decided.</span></div>`
    : `<div class="alert ok">${I.check}<span><b>Ready to publish.</b> Every field has been decided by a reviewer.</span></div>`;
  const F = [["all", "All", recs.length], ["attention", "Needs attention", recs.filter(needsAttention).length], ["conflict", "Conflicts", c.conflict],
    ["not_found", "Empty", c.empty], ["open", "Undecided", open]];
  h += `<div class="bar-row"><div class="seg">${F.map(([k, l, n]) => `<button data-filter="${k}" class="${filter === k ? "on" : ""}">${l}<span class="n">${n}</span></button>`).join("")}</div>
    <span class="sp"></span><label class="chk"><input type="checkbox" id="sort" ${store.get("skb-sort", false) ? "checked" : ""}> Least certain first</label></div>`;
  let list = recs.filter(r => filter === "all" || (filter === "attention" && needsAttention(r)) || (filter === "open" && !decisions[key(current, r.field)]) || r.status === filter);
  if (store.get("skb-sort", false)) list = [...list].sort((a, b) => (a.status === "conflict" ? -1 : a.confidence) - (b.status === "conflict" ? -1 : b.confidence));
  h += list.length ? list.map(fieldCard).join("") : `<div class="card empty-state">Nothing here.</div>`;
  document.getElementById("main").innerHTML = h;
  document.querySelectorAll("[data-filter]").forEach(b => b.onclick = () => { filter = b.dataset.filter; renderReview(); });
  document.getElementById("sort").onchange = e => { store.set("skb-sort", e.target.checked); renderReview(); };
  document.querySelectorAll("main [data-a]").forEach(b => b.onclick = () => act(b.dataset.a, b.dataset.f, b.dataset.i));
}

function act(a, f, i) {
  const r = DATA.records[current].find(x => x.field === f), k = key(current, f);
  if (a === "undo") delete decisions[k];
  else if (a === "approve") decisions[k] = {decision: "approved", value: r.value};
  else if (a === "confirm_empty") decisions[k] = {decision: "confirmed empty", value: null};
  else if (a === "pick") decisions[k] = {decision: "conflict resolved", value: r.candidates[i].value, chosen_source: r.candidates[i].source_ref};
  else if (a === "edit") {
    const v = document.querySelector(`input[data-in="${f}"]`).value.trim();
    if (!v) return;
    decisions[k] = {decision: "corrected", value: v, ai_value: r.status === "conflict" ? r.candidates.map(c => c.value) : r.value};
  }
  const c = counts(current);
  timers[current].end = c.done === c.total ? Date.now() : null;
  store.set(KEY, decisions); store.set(KEY + "-timers", timers);
  renderReview();
}

function renderAccuracy() {
  const E = DATA.eval, el = document.getElementById("v-accuracy");
  if (!E) { el.innerHTML = `<div class="card empty-state">Run <code>python -m skb all</code> to produce the evaluation.</div>`; return; }
  const R = E.readiness;
  let h = `<h2 class="h">How good is the draft?</h2><p class="lead">Scored field by field against hand-checked answers for ${E.n_schemes} schemes (${E.n_fields} fields).
    <b>Field-level accuracy</b> = out of every 100 fields the AI pre-fills, how many a researcher can accept without retyping. <b>Dangerous errors</b> are wrong values that look right; they are the ones that could reach a family.</p>`;
  h += `<div class="card verdict"><div class="big" style="background:${R.ready ? "var(--ok-soft)" : "var(--warn-soft)"};color:${R.ready ? "var(--ok)" : "var(--warn)"}">${R.ready ? I.check : I.warn}</div>
    <div><h2>${R.ready ? "Ready to scale to 5,000 schemes" : "Not ready to scale yet"}</h2><p>${R.checks.filter(c => c.passed).length} of ${R.checks.length} readiness checks pass. ${R.ready ? "" : "The sample is a demonstration set; the real decision needs ~100 real, held-out schemes."}</p></div></div>`;
  h += `<div class="kpis"><div class="card kpi"><small>Field-level accuracy</small><b>${pct(E.accuracy)}</b></div>
    <div class="card kpi ${E.dangerous_error_rate ? "bad" : "ok"}"><small>Dangerous errors</small><b>${pct(E.dangerous_error_rate)}</b></div>
    <div class="card kpi"><small>Safe errors (left empty)</small><b>${pct(E.safe_error_rate)}</b></div>
    <div class="card kpi"><small>Conflict recall</small><b>${pct(E.conflict_recall)}</b></div>
    <div class="card kpi"><small>Grounding rate</small><b>${pct(E.grounding_rate)}</b></div></div>`;
  h += `<div class="card pad" style="margin-bottom:16px"><div class="sec-h">Readiness checks (go / no-go before 5,000 schemes)</div><table><tr><th></th><th>Check</th><th>Rule</th><th>Actual</th><th>Why it matters</th></tr>` +
    R.checks.map(c => `<tr><td style="color:${c.passed ? "var(--ok)" : "var(--bad)"}">${c.passed ? I.check : I.x}</td><td><b>${esc(c.check)}</b></td><td><code>${esc(c.metric)} ${esc(c.rule)}</code></td>
    <td>${c.metric === "n_schemes" ? c.actual : pct(c.actual)}</td><td style="color:var(--muted)">${esc(c.why)}</td></tr>`).join("") + `</table></div>`;
  const rows = obj => Object.entries(obj).map(([k, v]) => `<tr><td>${esc(LABEL[k] || k)}${HIGH.has(k) ? ' <span class="tag acc">High stakes</span>' : ""}</td><td>${v.n}</td>
    <td><div style="display:flex;align-items:center;gap:10px"><div class="hbar" style="flex:1"><i style="width:${v.accuracy * 100}%"></i></div><span>${pct(v.accuracy)}</span></div></td>
    <td>${v.dangerous ? `<span class="tag bad">${v.dangerous}</span>` : "0"}</td><td>${v.safe_errors}</td></tr>`).join("");
  const head = `<tr><th></th><th>Fields</th><th>Accuracy</th><th>Dangerous</th><th>Safe errors</th></tr>`;
  h += `<div class="two"><div class="card pad"><div class="sec-h">By document type</div><table>${head}${rows(E.per_doc_type)}</table></div>
    <div class="card pad"><div class="sec-h">By field</div><table>${head}${rows(E.per_field)}</table></div></div>`;
  const misses = E.rows.filter(r => !["correct", "correct_empty", "conflict_caught"].includes(r.outcome));
  const DANGER = new Set(["wrong_value", "false_fill", "conflict_missed"]);
  h += `<div class="card pad" style="margin-top:16px"><div class="sec-h">Every field that was not correct</div>` + (misses.length ? `<table><tr><th>Scheme</th><th>Field</th><th>Document</th><th>Outcome</th><th>Draft</th><th>Truth</th></tr>` +
    misses.map(r => `<tr><td>${r.scheme_ref}</td><td>${LABEL[r.field]}</td><td>${esc(r.doc_type)}</td><td><span class="tag ${DANGER.has(r.outcome) ? "bad" : ""}">${r.outcome.replace("_", " ")}</span></td>
    <td>${STATUS[r.pred_status]}</td><td>${STATUS[r.gold_status]}</td></tr>`).join("") + `</table>` : `<p>None.</p>`) + `</div>`;
  const done = Object.entries(timers).filter(([, t]) => t.end);
  h += `<div class="card pad" style="margin-top:16px"><div class="sec-h">Is checking faster than typing?</div><p style="margin:0;color:var(--muted)">${done.length
    ? `Reviewed ${done.length} scheme(s) in this browser, average <b style="color:var(--ink)">${Math.round(done.reduce((a, [, t]) => a + (t.end - t.start), 0) / done.length / 1000)} s</b> per scheme. Compare with the time a researcher takes to type the same scheme from scratch in a pilot.`
    : "Finish reviewing a scheme to record how long checking took. The time is included in the exported decisions."}</p></div>`;
  el.innerHTML = h;
}

function renderMethod() {
  const steps = [["Read", "loaders.py", "Opens PDFs, scans, web pages, press notes and MyScheme listings. Every line keeps its page or section; a PDF with no text layer is flagged as a scan."],
    ["Extract", DATA.mode === "llm" ? "extract_llm.py · Groq" : "extract_rules.py", DATA.mode === "llm" ? `GPT-OSS reads the numbered lines and returns each field with exact quotes. Scans are first transcribed by a vision model.` : "Finds sections by English, Hindi and Marathi headings and reads each field. Understands ₹ १०,०००, lakh commas and Marathi dates."],
    ["Check the proof", "verify.py", "A value survives only if its quote is literally in the source. Anything else is dropped with the reason, which stops invented answers."],
    ["Compare sources", "reconcile.py", "Agreement raises confidence. Disagreement becomes a conflict with both values kept. An unreadable official document leaves money and date fields empty."],
    ["Human review", "review.html", "A researcher approves, corrects or picks a side. Nothing is publishable until every field has a decision; the time taken is recorded."],
    ["Measure and learn", "evaluate.py · feedback.py", "Scores the draft against checked answers, checks readiness thresholds, and turns reviewer decisions into new test answers."]];
  const outcomes = [["Correct / correctly empty / conflict caught", "ok", "Saves the researcher time"], ["Missed (left empty)", "", "Safe: researcher types it, as today"],
    ["False conflict", "", "Safe: seconds to dismiss"], ["Wrong value / invented value / hidden conflict", "bad", "Dangerous: could reach a family"]];
  document.getElementById("v-method").innerHTML = `<h2 class="h">How the draft is made</h2><p class="lead">AI prepares a first draft of each scheme record. A person checks it. Only approved values reach the agent app.</p>
    <div class="rules"><div class="card rule"><b>A person always checks before anything goes live</b><p>The draft is locked as "not publishable" until every field has a reviewer's decision.</p></div>
    <div class="card rule"><b>Every fact points back to its source</b><p>Each value shows the exact quote, page or section, source and capture date. No quote, no value.</p></div></div>
    <div class="steps">${steps.map(([t, f, d], i) => `<div class="card step"><div class="no">${i + 1}</div><b>${t}</b><p><code>${f}</code></p><p style="margin-top:6px">${d}</p></div>`).join("")}</div>
    <div class="card pad" style="margin-top:16px"><div class="sec-h">How each field is scored</div><table><tr><th>Outcome</th><th>Effect</th></tr>
    ${outcomes.map(([o, c, e]) => `<tr><td><span class="tag ${c}">${o}</span></td><td>${e}</td></tr>`).join("")}</table></div>`;
}

const themeBtn = document.getElementById("theme");
function setTheme(t) { document.documentElement.dataset.theme = t; themeBtn.innerHTML = t === "dark" ? I.sun : I.moon; store.set("skb-theme", t); }
setTheme(store.get("skb-theme", "light"));
themeBtn.onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
function showTab(name) {
  document.querySelectorAll(".tab").forEach(x => x.classList.toggle("on", x.dataset.v === name));
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("on", v.id === "v-" + name));
  if (name === "accuracy") renderAccuracy();
  history.replaceState(null, "", "#" + name);
}
document.querySelectorAll(".tab").forEach(t => t.onclick = () => showTab(t.dataset.v));
document.getElementById("engine").innerHTML = '<span class="dot"></span>' + (DATA.mode === "llm"
  ? `Groq · ${esc(DATA.meta.models.text)}` : "Offline rules extractor");
document.getElementById("export").onclick = () => {
  const out = Object.entries(decisions).map(([k, d]) => {
    const s = k.split("::")[0], t = timers[s];
    return {scheme_ref: s, field: k.split("::")[1], ...d, reviewed_at: new Date().toISOString(),
      scheme_review_seconds: t && t.end ? Math.round((t.end - t.start) / 1000) : null};
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], {type: "application/json"}));
  a.download = "review_decisions.json"; a.click();
};
setInterval(() => { const c = document.getElementById("clock"); if (c) c.textContent = elapsed(current); }, 1000);
renderReview(); renderMethod();
if (["accuracy", "method"].includes(location.hash.slice(1))) showTab(location.hash.slice(1));
</script></body></html>
"""


def build(out_dir: Path, mode: str) -> None:
    read = lambda name: json.loads((out_dir / name).read_text(encoding="utf-8")) if (out_dir / name).exists() else None
    payload = {"mode": mode, "records": read(f"records_{mode}.json"), "meta": read(f"run_{mode}.json"),
               "eval": read(f"eval_{mode}.json")}
    safe = lambda obj: json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", safe(payload)).replace("__HIGH__", safe(sorted(HIGH_STAKES)))
    (out_dir / "review.html").write_text(html, encoding="utf-8")
