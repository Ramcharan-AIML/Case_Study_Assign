"""Builds out/review.html: the screen a researcher uses to check the AI draft.

Design goal from the brief: checking must be faster than typing. So each field
shows the value next to the exact quote and where it is, conflicts show both
sides with a one-click choice, and low-confidence fields sort to the top.
Decisions export as JSON, which is the format that grows the gold test set.
"""
from __future__ import annotations

import json
from pathlib import Path

from .pipeline import load_manifest

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scheme Draft Review</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--ink:#1d1d1b;--mute:#6b6a65;--line:#e4e2dc;--found:#1f7a4d;--found-bg:#e6f4ec;
--conf:#a3361d;--conf-bg:#fbe9e4;--nf:#6b6a65;--nf-bg:#efeee9;--warn:#8a5a00;--warn-bg:#fdf3dc;--acc:#2b4cc4}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--ink:#ecebe6;--mute:#a09f99;--line:#33322f;
--found:#6fcf9b;--found-bg:#1d3328;--conf:#f08a70;--conf-bg:#3a221c;--nf:#a09f99;--nf-bg:#2a2a27;--warn:#e7b85c;--warn-bg:#352b17;--acc:#8ea6ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,"Segoe UI","Nirmala UI",sans-serif}
header{padding:18px 24px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header h1{font-size:18px;margin:0}header .sub{color:var(--mute);font-size:13px}
header .sp{flex:1}button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:6px 12px;cursor:pointer}
button.primary{background:var(--acc);border-color:var(--acc);color:#fff}button:hover{filter:brightness(.97)}
.wrap{display:grid;grid-template-columns:260px 1fr;min-height:calc(100vh - 66px)}
nav{border-right:1px solid var(--line);padding:12px}nav .s{padding:10px 12px;border-radius:10px;cursor:pointer;margin-bottom:6px}
nav .s.on{background:var(--card);box-shadow:0 0 0 1px var(--line)}nav .s b{display:block;font-size:14px}nav .s small{color:var(--mute)}
main{padding:20px 24px;max-width:1100px}
.src{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 18px}.src a{font-size:12.5px;color:var(--acc);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:3px 10px;background:var(--card)}
.gate{padding:12px 14px;border-radius:10px;margin-bottom:16px;font-size:14px}
.gate.no{background:var(--warn-bg);color:var(--warn)}.gate.ok{background:var(--found-bg);color:var(--found)}
.f{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:12px}
.f.decided{opacity:.62}.top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.name{font-weight:600}.chip{font-size:12px;padding:2px 9px;border-radius:999px;font-weight:600}
.found{background:var(--found-bg);color:var(--found)}.conflict{background:var(--conf-bg);color:var(--conf)}.not_found{background:var(--nf-bg);color:var(--nf)}
.bar{width:70px;height:6px;background:var(--line);border-radius:3px;overflow:hidden}.bar i{display:block;height:100%;background:var(--acc)}
.cf{font-size:12px;color:var(--mute)}.val{font-size:16px;margin:8px 0 4px}.val ul{margin:4px 0;padding-left:20px}
.ev{border-left:3px solid var(--line);padding:4px 10px;margin:6px 0;font-size:13.5px}.ev q{display:block}.ev small{color:var(--mute)}
.note{font-size:13px;color:var(--mute);margin-top:6px}.cands{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-top:8px}
.cand{border:1px solid var(--line);border-radius:10px;padding:10px}.acts{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;align-items:center}
.acts input{flex:1;min-width:200px;font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
.dec{font-size:13px;font-weight:600;color:var(--found)}mark{background:#ffe58a;color:#1d1d1b;border-radius:3px;padding:0 2px}
@media (max-width:760px){.wrap{grid-template-columns:1fr}nav{border-right:0;border-bottom:1px solid var(--line);display:flex;overflow-x:auto;gap:6px}nav .s{min-width:180px}main{padding:16px}}
</style></head><body>
<header><div><h1>Scheme draft review</h1><div class="sub">AI draft · nothing is published until every field is decided by a person · extractor: <b id="mode"></b></div></div>
<span class="sp"></span><label class="cf"><input type="checkbox" id="sort"> Least certain first</label>
<button id="export" class="primary">Export decisions (JSON)</button></header>
<div class="wrap"><nav id="nav"></nav><main id="main"></main></div>
<script>
const DATA = __DATA__;
const SOURCES = __SOURCES__;
const LABEL = {scheme_name:"Scheme name",department:"Department",benefit_type:"Benefit type",benefit_amount:"Benefit amount",
 benefit_frequency:"Benefit frequency",eligibility:"Eligibility",documents_required:"Documents required",how_to_apply:"How to apply",
 deadline:"Deadline",official_link:"Official link"};
const KEY = "skb-review-" + DATA.mode;
let decisions = {};
try { decisions = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(decisions)); } catch (e) {} };
let current = Object.keys(DATA.records)[0];
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt = (f, v) => v == null ? "<i>empty</i>" : Array.isArray(v) ? "<ul>" + v.map(x => "<li>" + esc(x) + "</li>").join("") + "</ul>"
  : f === "benefit_amount" ? "₹ " + Number(v).toLocaleString("en-IN") : f === "official_link" ? `<a href="${esc(v)}">${esc(v)}</a>` : esc(v);
const evHtml = e => `<div class="ev"><q>${esc(e.quote)}</q><small>${esc(e.location)} · ${esc(e.source_ref)} · ${esc(e.source_link)} · captured ${esc(e.captured_at)}</small></div>`;
const key = (s, f) => s + "::" + f;

function nav() {
  document.getElementById("nav").innerHTML = Object.entries(DATA.records).map(([s, recs]) => {
    const c = recs.filter(r => r.status === "conflict").length, n = recs.filter(r => r.status === "not_found").length;
    const done = recs.filter(r => decisions[key(s, r.field)]).length;
    return `<div class="s ${s === current ? "on" : ""}" data-s="${s}"><b>${s}</b><small>${done}/${recs.length} decided · ${c} conflict · ${n} empty</small></div>`;
  }).join("");
  document.querySelectorAll("nav .s").forEach(el => el.onclick = () => { current = el.dataset.s; render(); });
}

function render() {
  nav();
  document.getElementById("mode").textContent = DATA.mode;
  let recs = [...DATA.records[current]];
  if (document.getElementById("sort").checked) recs.sort((a, b) => (a.status === "conflict" ? -1 : a.confidence) - (b.status === "conflict" ? -1 : b.confidence));
  const open = recs.filter(r => !decisions[key(current, r.field)]).length;
  const srcs = SOURCES.filter(s => s.scheme_ref === current).map(s => `<a href="../data/${esc(s.path)}" target="_blank">${esc(s.source_ref)} · ${esc(s.authority)} · ${esc(s.language)} · ${esc(s.title)}</a>`).join("");
  let h = `<div class="src">${srcs}</div>` + (open ? `<div class="gate no">Not publishable: ${open} field(s) still need a decision.</div>`
    : `<div class="gate ok">All fields decided by a reviewer. Ready to publish this version.</div>`);
  for (const r of recs) {
    const d = decisions[key(current, r.field)];
    h += `<div class="f ${d ? "decided" : ""}"><div class="top"><span class="name">${LABEL[r.field]}</span>
      <span class="chip ${r.status}">${r.status.replace("_", " ")}</span>
      <span class="bar" title="confidence"><i style="width:${Math.round(r.confidence * 100)}%"></i></span><span class="cf">${r.confidence.toFixed(2)}</span>
      ${d ? `<span class="dec">✓ ${esc(d.decision)}</span>` : ""}</div>`;
    if (r.status === "conflict") {
      h += `<div class="cands">` + r.candidates.map((c, i) => `<div class="cand"><div class="val">${fmt(r.field, c.value)}</div>${c.evidence.map(evHtml).join("")}
        <button data-a="pick" data-f="${r.field}" data-i="${i}">Use this value</button></div>`).join("") + `</div>`;
    } else {
      h += `<div class="val">${fmt(r.field, r.value)}</div>` + r.evidence.map(evHtml).join("");
    }
    if (r.note) h += `<div class="note">${esc(r.note)}</div>`;
    h += `<div class="acts">${r.status === "found" ? `<button data-a="approve" data-f="${r.field}">Approve</button>` : ""}
      ${r.status === "not_found" ? `<button data-a="confirm_empty" data-f="${r.field}">Confirm empty</button>` : ""}
      <input placeholder="Correct value (and say why)" data-in="${r.field}"><button data-a="edit" data-f="${r.field}">Save correction</button>
      ${d ? `<button data-a="undo" data-f="${r.field}">Undo</button>` : ""}</div></div>`;
  }
  document.getElementById("main").innerHTML = h;
  document.querySelectorAll("main button[data-a]").forEach(b => b.onclick = () => act(b.dataset.a, b.dataset.f, b.dataset.i));
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
  save(); render();
}

document.getElementById("sort").onchange = render;
document.getElementById("export").onclick = () => {
  const out = Object.entries(decisions).map(([k, d]) => ({scheme_ref: k.split("::")[0], field: k.split("::")[1], ...d, reviewed_at: new Date().toISOString()}));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], {type: "application/json"}));
  a.download = "review_decisions.json"; a.click();
};
render();
</script></body></html>
"""


def build(records_path: Path, data_dir: Path, out_path: Path, mode: str) -> None:
    records = json.loads(records_path.read_text(encoding="utf-8"))
    sources = [s.model_dump() for s in load_manifest(data_dir)]
    safe = lambda obj: json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", safe({"mode": mode, "records": records})).replace("__SOURCES__", safe(sources))
    out_path.write_text(html, encoding="utf-8")
