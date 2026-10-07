"""Статичний експорт для GitHub Pages: docs/index.html + docs/data.json.

Сторінка самодостатня (CSS та JS вбудовані, фільтрація на клієнті),
тому працює на Pages без жодного сервера.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import config
from . import tracks as tracks_mod
from . import budget as budget_mod
from .db import Database

HTML = """<!DOCTYPE html>
<html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Грант-радар КП</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--panel2:#1e222b;--line:#2a2f3a;--txt:#e8eaef;
--muted:#9aa3b2;--accent:#4f9cf9;--high:#ff6b4a;--med:#f4b740;--low:#6b7280}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header{background:linear-gradient(135deg,#182033,#101520);border-bottom:1px solid var(--line);padding:22px 28px}
h1{margin:0 0 4px;font-size:22px}.sub{color:var(--muted);font-size:13px}
.wrap{max-width:1180px;margin:0 auto;padding:22px 28px 60px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.stat b{display:block;font-size:26px}.stat span{color:var(--muted);font-size:12px;text-transform:uppercase}
.filters{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;
display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}
input,select{background:var(--panel2);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:8px 11px;font-size:14px}
input[type=text]{min-width:240px}
.card{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--low);
border-radius:12px;padding:16px 18px;margin-bottom:12px}
.card.high{border-left-color:var(--high)}.card.medium{border-left-color:var(--med)}
.card h3{margin:0 0 6px;font-size:16.5px;line-height:1.35}
.meta{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0;font-size:12.5px;color:var(--muted)}
.tag{background:var(--panel2);border:1px solid var(--line);border-radius:999px;padding:2px 10px}
.tag.score{background:#20283a;color:#cfe3ff;border-color:#2e3b55;font-weight:600}
.tag.dl{background:#3a1c14;color:#ff8c69;border-color:#6b3324}
.sum{color:#c7cdd9;font-size:14px}
h2.gh{font-size:15px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);
margin:26px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h2.gh span{background:var(--panel2);border:1px solid var(--line);border-radius:999px;padding:1px 9px;font-size:12px;margin-left:6px}
.tag.benef{font-weight:600}
.tag.track{font-weight:600;background:#1b2520;color:#b9e7c4;border-color:#2c4635}
.tag.t-education{background:#241c30;color:#dcb6f8;border-color:#3f2b52}
.tag.t-transport{background:#1d2430;color:#a9c8f0;border-color:#30415a}
.tag.t-business{background:#2a2416;color:#f0cf96;border-color:#4b3d20}
.tag.t-other{background:#1e222b;color:#9aa3b2}
.tag.origin{background:#132a1f;color:#8ff0b5;border-color:#1f5236;font-weight:600}
.links{margin:8px 0 2px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.donorbtn{background:#2a3350!important;border-color:#3d4a73!important;color:#dce6ff!important}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 10px}
.tab{display:flex;align-items:center;gap:7px;padding:9px 15px;border-radius:10px;cursor:pointer;
     border:1px solid #273043;background:#141924;color:#9aa3b2;font-size:14px;font-family:inherit}
.tab b{background:#1e2636;color:#cfd8e8;border-radius:20px;padding:1px 9px;font-size:12.5px}
.tab:hover{border-color:#3a4a66;color:#cfd8e8}
.tab.on{background:#17304a;border-color:#2f6ea6;color:#e8f1ff}
.tab.on b{background:#235080;color:#fff}
.applybtn{background:#1f7a4d;color:#eafff3;border:1px solid #2e9e66;border-radius:8px;
          padding:6px 12px;font-size:13px;font-weight:600;text-decoration:none}
.src{color:#9aa3b2;font-size:12.5px;text-decoration:none;border-bottom:1px dotted #475}
.tag.money{background:#14262a;color:#8fe3e8;border-color:#1f4650;font-weight:600}
.tag.equip{background:#33230f;color:#ffc07a;border-color:#60421c;font-weight:600}.tag.b-communal{background:#15291f;color:#7ee2b8;border-color:#23523c}
.tag.b-private{background:#1a2133;color:#9cc4ff;border-color:#2e3b55}
.tag.b-both{background:#2a2416;color:#f6cf7a;border-color:#51431f}
.llm{background:#121a26;border:1px solid #1f3147;border-radius:10px;padding:10px 12px;margin-top:10px;font-size:13.5px}
.llm b{color:#8fc0ff}.why{color:var(--muted);font-size:12px;margin-top:8px;font-style:italic}
footer{color:var(--muted);font-size:12px;text-align:center;padding:20px}
</style></head><body>
<header><h1>🛰️ Грант-радар для комунальних підприємств</h1>
<div class="sub">__ORG__ · оновлено __UPDATED__ (автоматично, GitHub Actions)</div></header>
<div class="wrap">
<div class="stats">
<div class="stat"><b>__TOTAL__</b><span>усього</span></div>
<div class="stat"><b style="color:var(--high)">__HIGH__</b><span>висока релевантність</span></div>
<div class="stat"><b style="color:var(--med)">__MED__</b><span>середня</span></div>
<div class="stat"><b>__SOON__</b><span>дедлайн ≤ 30 днів</span></div>
<div class="stat"><b style="color:#7ee2b8">__COMM__</b><span>🏛 для комунальних</span></div>
<div class="stat"><b style="color:#9cc4ff">__PRIV__</b><span>🏭 для приватних</span></div>
<div class="stat"><b style="color:#ffd966">__UA__</b><span>🇺🇦 українських</span></div>
<div class="stat"><b style="color:#8ff0b5">__RESOLVED__</b><span>🔗 з першоджерелом</span></div>
<div class="stat" title="новини без першоджерела, вакансії, протерміновані"><b style="color:#7a8599">__HIDDEN__</b><span>🚫 відсіяно</span></div>
<div class="stat"><b style="color:#9be8a0">__WASTE__</b><span>♻️ відходи</span></div>
<div class="stat"><b style="color:#d7a8f5">__EDU__</b><span>🎓 освіта</span></div>
<div class="stat"><b style="color:#ffc07a">__EQUIP__</b><span>🚛 техніка / контейнери</span></div>
<div class="stat"><b style="color:#8fe3e8">__BUDSM__</b><span>💶 до 500 тис. €</span></div>
</div>
<div class="tabs">
  <button class="tab on" data-feed="ua">🇺🇦 Україна — пряме фінансування <b id="cnt_ua">0</b></button>
  <button class="tab" data-feed="eu">🇪🇺 ЄС — консорціумні проєкти <b id="cnt_eu">0</b></button>
  <button class="tab" data-feed="aid">🤝 Побратими та техніка <b id="cnt_aid">0</b></button>
  <button class="tab" data-feed="edu">🎓 Освітній напрям <b id="cnt_edu">0</b></button>
  <button class="tab" data-feed="all">🌍 Усе разом <b id="cnt_all">0</b></button>
  <a class="tab" href="donors.html" style="text-decoration:none">📇 Реєстр донорів <b id="cnt_don">0</b></a>
  <a class="tab" href="danube.html" style="text-decoration:none">🌊 Дунай</a>
  <a class="tab" href="cities_big.html" style="text-decoration:none">🏙 Великі громади</a>
  <a class="tab" href="cities_green.html" style="text-decoration:none">🌱 Зелені</a>
</div>
<div class="filters">
<input type="text" id="q" placeholder="пошук: відходи, waste, Interreg…">
<select id="band"><option value="">усі рівні</option><option value="high">🔥 висока</option>
<option value="medium">🟡 середня</option><option value="low">⚪ низька</option></select>
<select id="region"><option value="">усі регіони</option><option value="EU">🇪🇺 ЄС</option>
<option value="UA">🇺🇦 Україна</option><option value="INT">🌍 міжнародні</option></select>
<select id="track"><option value="">усі напрями</option>__TRACK_OPTIONS__</select>
<select id="budget"><option value="">будь-який бюджет</option>
<option value="s">💶 до 100 тис. €</option>
<option value="m">💶 100–500 тис. €</option>
<option value="l">💶 понад 500 тис. €</option>
<option value="unknown">💶 суму не вказано</option></select>
<label style="color:#9aa3b2;font-size:13px;display:flex;align-items:center;gap:6px">
<input type="checkbox" id="equip"> 🚛 лише з технікою</label>
<label style="color:#9aa3b2;font-size:13px;display:flex;align-items:center;gap:6px">
<input type="checkbox" id="applyonly"> 🔗 є посилання на подачу</label>
<select id="groupby"><option value="track">групувати за напрямом</option>
<option value="benef">групувати за типом заявника</option>
<option value="">єдиним списком</option></select>
<select id="benef"><option value="">усі типи заявників</option>
<option value="communal">🏛 комунальні / ОМС</option><option value="private">🏭 приватний бізнес</option>
<option value="both">🤝 обидва</option><option value="unknown">❔ уточнити</option></select>
<select id="order"><option value="score">за релевантністю</option>
<option value="deadline">за дедлайном</option><option value="newest">найновіші</option>
<option value="budget">за бюджетом ↓</option><option value="budget_asc">за бюджетом ↑</option></select>
</div>
<div id="list"></div></div>
<footer>Згенеровано агентом «Грант-радар КП» · <a href="data.json">data.json</a></footer>
<script>
const DATA = __DATA__;
const BL = {high:"🔥 Висока", medium:"🟡 Середня", low:"⚪ Низька"};
const NL = {communal:"🏛 Комунальні / ОМС", private:"🏭 Приватний бізнес",
            both:"🤝 Комунальні + приватні", unknown:"❔ Тип уточнити"};
const TL = __TRACK_LABELS__;
const TS = __TRACK_SHORT__;
const TORDER = __TRACK_ORDER__;
const esc = s => (s||"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function card(d){return `
    <div class="card ${d.band}">
      <h3><a href="${esc(d.apply_url || d.article_url || d.url)}" target="_blank" rel="noopener">${esc(d.title)}</a></h3>
      <div class="meta">
        <span class="tag score">${d.score}/100 ${BL[d.band]||""}</span>
        <span class="tag track t-${d.track||"other"}">${TS[d.track||"other"]||""}</span>
        ${d.equipment?'<span class="tag equip">🚛 техніка / контейнери</span>':""}
        ${d.apply_host?`<span class="tag origin" title="першоджерело — тут подають заявку">🔗 ${esc(d.apply_host)}</span>`:""}
        ${d.budget_human?`<span class="tag money" title="орієнтовна сума на проєкт">💶 ${d.budget_human}</span>`:""}
        <span class="tag benef b-${d.beneficiary||"unknown"}">${NL[d.beneficiary||"unknown"]}</span>
        <span class="tag">${esc(d.source_name)}</span>
        ${d.days_left!=null?`<span class="tag dl">⏳ ${d.days_left} дн. — ${(d.deadline_at||"").slice(0,10)}</span>`:""}
      </div>
      ${d.llm_summary?`<div class="llm"><b>AI-аналіз:</b> ${esc(d.llm_summary)}
        ${d.llm_fit?`<div style="margin-top:6px"><b>Чи підходить:</b> ${esc(d.llm_fit)}</div>`:""}
        ${d.llm_actions?`<div style="margin-top:6px"><b>Наступні кроки:</b> ${esc(d.llm_actions)}</div>`:""}</div>`
        :`<p class="sum">${esc((d.summary||"").slice(0,400))}</p>`}
      ${d.apply_url?`<div class="links">
        <a class="applybtn ${(d.apply_label||"").startsWith("сторінка донора")?"donorbtn":""}" href="${esc(d.apply_url)}"
           target="_blank" rel="noopener" title="${esc(d.apply_label||"")}">${(d.apply_label||"").startsWith("сторінка донора")?"🏛 Сайт донора — шукати конкурс":"🔗 Подати заявку / першоджерело"}</a>
        <a class="src" href="${esc(d.article_url||d.url)}" target="_blank" rel="noopener">ℹ️ анонс (${esc(d.source_name)})</a>
      </div>`:""}
      <div class="why">чому показано: ${esc(d.reasons||"")}</div>
    </div>`;}
function section(title, items){
  return `<h2 class="gh">${title}<span>${items.length}</span></h2>` + items.map(card).join("");
}
function render(){
  const fd=window.FEED||"ua",
        q=document.getElementById("q").value.toLowerCase(),
        b=document.getElementById("band").value,
        r=document.getElementById("region").value,
        tr=document.getElementById("track").value,
        bu=document.getElementById("budget").value,
        ap=document.getElementById("applyonly").checked,
        eq=document.getElementById("equip").checked,
        n=document.getElementById("benef").value,
        g=document.getElementById("groupby").value,
        o=document.getElementById("order").value;
  let rows=DATA.filter(d=>(!b||d.band===b)&&(!r||d.region===r)&&
    (!tr||(d.track||"other")===tr)&&(!eq||d.equipment)&&
    (!bu||(d.budget_band||"unknown")===bu)&&(!ap||d.apply_url)&&
    (fd==="all"||(d.feed||"ua")===fd)&&
    (!n||d.beneficiary===n||(n!=="unknown"&&d.beneficiary==="both"))&&
    (!q||((d.title+" "+(d.summary||"")+" "+(d.llm_summary||"")).toLowerCase().includes(q))));
  rows.sort((x,y)=> o==="score" ? y.score-x.score
    : o==="budget" ? ((y.budget_eur??-1)-(x.budget_eur??-1))
    : o==="budget_asc" ? ((x.budget_eur??Infinity)-(y.budget_eur??Infinity))
    : o==="deadline" ? ((x.days_left??9999)-(y.days_left??9999))
    : String(y.first_seen||"").localeCompare(String(x.first_seen||"")));
  let html="";
  if(g==="track" && !tr){
    const present=[...new Set(rows.map(d=>d.track||"other"))]
      .sort((a,b2)=>TORDER.indexOf(a)-TORDER.indexOf(b2));
    for(const key of present){
      const part=rows.filter(d=>(d.track||"other")===key);
      if(part.length) html+=section(TL[key]||key, part);
    }
  } else if(g==="benef" && !n){
    for(const key of ["communal","both","private","unknown"]){
      const part=rows.filter(d=>(d.beneficiary||"unknown")===key);
      if(part.length) html+=section(NL[key], part);
    }
  } else { html = rows.map(card).join(""); }
  document.getElementById("list").innerHTML = html ||
    '<p style="color:#9aa3b2;text-align:center;padding:40px">Нічого не знайдено</p>';
}
["q","band","region","track","budget","equip","applyonly","benef","groupby","order"].forEach(id=>{
  const el=document.getElementById(id);
  el.addEventListener("input",render); el.addEventListener("change",render);
});

// вкладки: 🇺🇦 пряме фінансування / 🇪🇺 консорціуми / 🤝 побратими й техніка / усе
window.FEED="ua";
document.getElementById("cnt_ua").textContent  = DATA.filter(d=>(d.feed||"ua")==="ua").length;
document.getElementById("cnt_eu").textContent  = DATA.filter(d=>(d.feed||"ua")==="eu").length;
document.getElementById("cnt_aid").textContent = DATA.filter(d=>(d.feed||"ua")==="aid").length;
document.getElementById("cnt_edu").textContent = DATA.filter(d=>(d.feed||"ua")==="edu").length;
document.getElementById("cnt_all").textContent = DATA.length;
if(window.DONOR_COUNT!==undefined){document.getElementById("cnt_don").textContent=window.DONOR_COUNT;}
document.querySelectorAll(".tab").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".tab").forEach(b=>b.classList.remove("on"));
    btn.classList.add("on");
    window.FEED=btn.dataset.feed;
    render();
  });
});
render();
</script></body></html>
"""


def export(db: Database, out_dir: Path | None = None, min_score: int = 12, limit: int = 1000) -> Path:
    out_dir = Path(out_dir or config.DOCS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = db.query(min_score=min_score, limit=limit, only_active=True)
    # вкладка 🤝 «Побратими та техніка»: тут бал не головне — навіть коротка
    # новина про передану техніку є контактом донора, тож беремо всі записи
    seen = {r["uid"] for r in rows}
    rows += [r for r in db.query(feed="aid", min_score=0, limit=400, only_active=True)
             if r["uid"] not in seen]
    seen |= {r["uid"] for r in rows}
    rows += [r for r in db.query(feed="edu", min_score=0, limit=400, only_active=True)
             if r["uid"] not in seen]
    rows.sort(key=lambda r: -(r.get("score") or 0))
    for r in rows:
        r.pop("raw_json", None)
        r["budget_human"] = budget_mod.human(r.get("budget_eur"))
    stats = db.stats()
    org = config.load_profile().get("organization", {})

    (out_dir / "data.json").write_text(
        json.dumps({"generated_at": datetime.now().isoformat(timespec="seconds"),
                    "stats": stats, "items": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    present = tracks_mod.ordered_tracks([r.get("track") or "other" for r in rows])
    track_options = "".join(
        f'<option value="{k}">{tracks_mod.LABEL.get(k, k)}</option>' for k in present)

    html = (HTML
            .replace("__DATA__", json.dumps(rows, ensure_ascii=False))
            .replace("__ORG__", f"{org.get('name', '')} · {org.get('region', '')}")
            .replace("__UPDATED__", datetime.now().strftime("%d.%m.%Y %H:%M"))
            .replace("__TOTAL__", str(stats["total"]))
            .replace("__HIGH__", str(stats["high"]))
            .replace("__MED__", str(stats["medium"]))
            .replace("__SOON__", str(stats["deadline_30d"]))
            .replace("__COMM__", str(stats.get("communal", 0)))
            .replace("__PRIV__", str(stats.get("private", 0)))
            .replace("__UA__", str(stats.get("ua", 0)))
            .replace("__RESOLVED__", str(stats.get("resolved", 0)))
            .replace("__HIDDEN__", str(stats.get("hidden", 0)))
            .replace("__WASTE__", str(stats.get("waste", 0)))
            .replace("__EDU__", str(stats.get("education", 0)))
            .replace("__EQUIP__", str(stats.get("equipment", 0)))
            .replace("__BUDSM__", str(sum(
                stats.get("budgets", {}).get(k, 0) for k in ("s", "m"))))
            .replace("__TRACK_LABELS__", json.dumps(tracks_mod.LABEL, ensure_ascii=False))
            .replace("__TRACK_SHORT__", json.dumps(tracks_mod.SHORT, ensure_ascii=False))
            .replace("__TRACK_ORDER__", json.dumps(
                tracks_mod.ordered_tracks(tracks_mod.TRACK_ORDER), ensure_ascii=False))
            .replace("__TRACK_OPTIONS__", track_options))
    html = html.replace("window.FEED=\"ua\";",
                        f'window.FEED="ua";window.DONOR_COUNT={db.donor_count()};')
    path = out_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    export_donors(db, out_dir)
    return path


DONORS_HTML = """<!DOCTYPE html>
<html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🤝 Реєстр донорів — Грант-радар</title>
<style>
 :root{--bg:#0f1115;--panel:#171a21;--panel2:#1e222b;--line:#2a2f3a;--txt:#e8eaef;--muted:#9aa3b2;--accent:#4f9cf9}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
 a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
 header{background:linear-gradient(135deg,#1b2433,#101520);border-bottom:1px solid var(--line);padding:22px 28px}
 h1{margin:0 0 4px;font-size:22px}.sub{color:var(--muted);font-size:13.5px}
 .wrap{max-width:1450px;margin:0 auto;padding:18px 22px 60px}
 .nav{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
 .nav a{padding:9px 15px;border-radius:10px;border:1px solid #273043;background:#141924;color:#9aa3b2;font-size:14px}
 .nav a.on{background:#17304a;border-color:#2f6ea6;color:#e8f1ff}
 .stats{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
 .stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 14px;min-width:115px}
 .stat b{display:block;font-size:20px}.stat span{color:var(--muted);font-size:12px}
 .filters{display:flex;gap:8px;flex-wrap:wrap;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;margin:12px 0}
 .filters input,.filters select{background:var(--panel2);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:14px}
 table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
 th,td{padding:10px 11px;border-bottom:1px solid var(--line);vertical-align:top;font-size:13.5px}
 th{background:#141a24;color:var(--muted);text-align:left;white-space:nowrap}
 tr:hover td{background:#1a1f29}
 .pri{font-weight:700;font-size:16px;border-radius:8px;padding:3px 9px;display:inline-block}
 .hot{background:#3a1a14;color:#ff9d84;border:1px solid #7a2f1f}
 .warm{background:#332a12;color:#f6cf7a;border:1px solid #6b571f}
 .cold{background:#20242e;color:#9aa3b2;border:1px solid #333a48}
 .formula{color:var(--muted);font-size:11.5px}
 .badge{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:20px;padding:2px 9px;font-size:12px;color:#cfd8e8;margin:0 4px 3px 0}
 button.copy{background:#14301f;border:1px solid #2e9e66;color:#9be8bb;border-radius:8px;padding:5px 10px;font-size:12.5px;cursor:pointer}
 button.show{background:#182438;border:1px solid #2e4a6b;color:#cfe0ff;border-radius:8px;padding:5px 10px;font-size:12.5px;cursor:pointer;margin-top:4px}
 .hint{background:#141a24;border:1px solid var(--line);border-radius:12px;padding:12px 15px;color:#b7c0cf;font-size:13px;margin:10px 0 14px}
 footer{color:var(--muted);font-size:12px;text-align:center;padding:22px}
</style></head><body>
<header><h1>🤝 Реєстр донорів і партнерів</h1>
<div class="sub">__ORG__ · пріоритет = Д (доведеність) + М (місток) + З (збіг потреби) − В (вартість входу) · оновлено __UPDATED__</div></header>
<div class="wrap">
 <div class="nav"><a href="index.html">← до стрічки грантів</a><a href="#" class="on">📇 Реєстр донорів</a><a href="danube.html">🌊 Дунай</a><a href="cities_big.html">🏙 Великі громади</a><a href="cities_green.html">🌱 Зелені</a></div>
 <div class="stats">
  <div class="stat"><b id="s_total">0</b><span>донорів</span></div>
  <div class="stat"><b id="s_hot" style="color:#ff6b4a">0</b><span>🔥 гарячі (7+)</span></div>
  <div class="stat"><b id="s_warm" style="color:#f4b740">0</b><span>🟡 теплі (4–6)</span></div>
  <div class="stat"><b id="s_cold" style="color:#6b7280">0</b><span>⚪ холодні</span></div>
 </div>
 <div class="hint">Реєстр потенційних донорів із контактами та балом пріоритету.
  Методологія пошуку: <b>docs/METODOLOGIA_DONORIV.md</b>, довідник каналів: <b>docs/PARTNERSTVA.md</b>.</div>
 <div class="filters">
  <input type="text" id="q" placeholder="пошук: донор, подія, отримувач…">
  <select id="circle"><option value="">усі кола</option></select>
  <select id="goods"><option value="">будь-яка допомога</option></select>
  <select id="country"><option value="">усі країни</option></select>
  <select id="minp"><option value="0">пріоритет ≥ 0</option><option value="4">пріоритет ≥ 4</option><option value="7">пріоритет ≥ 7</option></select>
 </div>
 <table><thead><tr><th>бал</th><th>донор</th><th>країна</th><th>тип</th><th>коло</th><th>допомога</th>
   <th>привід (що і кому передав)</th><th>контакти</th></tr></thead><tbody id="rows"></tbody></table>
</div>
<footer>Реєстр формується командою <code>python -m grant_radar donors</code> · CSV: <code>data/donors.csv</code></footer>
<script>
const D = __DONORS__, CIRCLES = __CIRCLES__, GOODS = __GOODS__, ORGS = __ORGS__, CN = __COUNTRIES__;
const esc = s => (s||"").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function fill(sel, obj, used){const el=document.getElementById(sel);
  Object.keys(obj).filter(k=>used.has(String(k))).forEach(k=>{
    const o=document.createElement("option");o.value=k;o.textContent=obj[k];el.appendChild(o);});}
fill("circle", CIRCLES, new Set(D.map(d=>String(d.circle))));
fill("goods", GOODS, new Set(D.map(d=>d.goods)));
fill("country", CN, new Set(D.map(d=>d.country)));
document.getElementById("s_total").textContent = D.length;
document.getElementById("s_hot").textContent = D.filter(d=>d.priority>=7).length;
document.getElementById("s_warm").textContent = D.filter(d=>d.priority>=4&&d.priority<7).length;
document.getElementById("s_cold").textContent = D.filter(d=>d.priority<4).length;
function render(){
  const q=document.getElementById("q").value.toLowerCase(),
        ci=document.getElementById("circle").value, go=document.getElementById("goods").value,
        co=document.getElementById("country").value, mp=+document.getElementById("minp").value;
  const list=D.filter(d=>(!ci||String(d.circle)===ci)&&(!go||d.goods===go)&&(!co||d.country===co)
      &&d.priority>=mp&&(!q||((d.name||"")+" "+(d.what||"")+" "+(d.recipient||"")).toLowerCase().includes(q)))
      .sort((a,b)=>b.priority-a.priority);
  document.getElementById("rows").innerHTML = list.map(d=>{
    const cls = d.priority>=7?"hot":(d.priority>=4?"warm":"cold");
    return `<tr><td><span class="pri ${cls}">${d.priority}</span>
      <div class="formula">Д${d.proven} М${d.bridge} З${d.need} −В${d.cost}</div></td>
      <td><b>${esc(d.name)}</b></td>
      <td>${esc(CN[d.country]||d.country)}<div class="formula">мова: ${esc(d.lang)}</div></td>
      <td><span class="badge">${esc(ORGS[d.org_type]||d.org_type)}</span></td>
      <td><span class="badge">${esc(CIRCLES[d.circle]||d.circle)}</span></td>
      <td><span class="badge">${esc(GOODS[d.goods]||d.goods)}</span></td>
      <td>${esc(d.what)}${d.recipient?`<div class="formula">отримувач: ${esc(d.recipient)}</div>`:""}
        ${d.event_date?`<div class="formula">${esc(d.event_date)}</div>`:""}
        ${d.news_url?`<div><a href="${esc(d.news_url)}" target="_blank">джерело ↗</a></div>`:""}</td>
      <td>${d.contact_email?`<a href="mailto:${esc(d.contact_email)}">${esc(d.contact_email)}</a>`:"<span class=\"badge\">немає</span>"}
        ${d.site?`<div><a href="${esc(d.site)}" target="_blank">сайт ↗</a></div>`:""}</td></tr>`;}).join("");
}
["q","circle","goods","country","minp"].forEach(id=>{
  const el=document.getElementById(id); el.addEventListener("input",render); el.addEventListener("change",render);});
render();
</script></body></html>
"""


def export_donors(db: Database, out_dir: Path | None = None) -> Path:
    """Окрема статична сторінка реєстру донорів: контакти й пріоритет."""
    from . import donors as donors_mod

    out_dir = Path(out_dir or config.DOCS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [r for r in db.donors(limit=2000)
            if not str(r.get("uid") or "").split(":")[0]
            in ("danube", "bigcity", "green")]
    org = config.load_profile().get("community", {})
    html = (DONORS_HTML
            .replace("__DONORS__", json.dumps(rows, ensure_ascii=False))
            .replace("__CIRCLES__", json.dumps(donors_mod.CIRCLE_LABEL, ensure_ascii=False))
            .replace("__GOODS__", json.dumps(donors_mod.GOODS_LABEL, ensure_ascii=False))
            .replace("__ORGS__", json.dumps(donors_mod.ORG_LABEL, ensure_ascii=False))
            .replace("__COUNTRIES__", json.dumps(donors_mod.COUNTRY_NAME, ensure_ascii=False))
            .replace("__ORG__", f"{org.get('name_uk', '')} · {org.get('region_uk', '')}")
            .replace("__UPDATED__", datetime.now().strftime("%d.%m.%Y %H:%M")))
    path = out_dir / "donors.html"
    path.write_text(html, encoding="utf-8")
    (out_dir / "donors.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


CHANNEL_HTML = """<!DOCTYPE html>
<html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — Грант-радар</title>
<style>
 :root{--bg:#0f1115;--panel:#171a21;--panel2:#1e222b;--line:#2a2f3a;--txt:#e8eaef;--muted:#9aa3b2;--accent:#4f9cf9}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
 a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
 header{background:linear-gradient(135deg,#102433,#101520);border-bottom:1px solid var(--line);padding:22px 28px}
 h1{margin:0 0 4px;font-size:22px}.sub{color:var(--muted);font-size:13.5px}
 .wrap{max-width:1400px;margin:0 auto;padding:18px 22px 60px}
 .nav{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
 .nav a{padding:9px 15px;border-radius:10px;border:1px solid #273043;background:#141924;color:#9aa3b2;font-size:14px}
 .nav a.on{background:#17304a;border-color:#2f6ea6;color:#e8f1ff}
 .stats{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
 .stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 14px;min-width:120px}
 .stat b{display:block;font-size:20px}.stat span{color:var(--muted);font-size:12px}
 .hint{background:#111a22;border:1px solid #23394a;border-radius:12px;padding:12px 15px;color:#b7c0cf;font-size:13px;margin:10px 0 14px}
 .filters{display:flex;gap:8px;flex-wrap:wrap;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;margin:12px 0}
 .filters input,.filters select{background:var(--panel2);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:14px}
 table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
 th,td{padding:9px 11px;border-bottom:1px solid var(--line);vertical-align:top;font-size:13.5px}
 th{background:#141a24;color:var(--muted);text-align:left;white-space:nowrap}
 tr:hover td{background:#1a1f29}
 .pri{font-weight:700;border-radius:8px;padding:3px 9px;display:inline-block}
 .hot{background:#3a1a14;color:#ff9d84;border:1px solid #7a2f1f}
 .warm{background:#332a12;color:#f6cf7a;border:1px solid #6b571f}
 .cold{background:#20242e;color:#9aa3b2;border:1px solid #333a48}
 .badge{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:20px;padding:2px 9px;font-size:12px;color:#cfd8e8}
 footer{color:var(--muted);font-size:12px;text-align:center;padding:22px}
</style></head><body>
<header><h1>__TITLE__</h1>
<div class="sub">__ORG__ · __SUB__ · оновлено __UPDATED__</div></header>
<div class="wrap">
 <div class="nav">__NAV__</div>
 <div class="stats" id="stats"></div>
 <div class="hint">__HINT__</div>
 <div class="filters">
  <input type="text" id="q" placeholder="пошук: місто, e-mail, мер, примітка…">
  <select id="country"><option value="">усі країни</option>__COUNTRY_OPTIONS__</select>
  <select id="mail"><option value="">усі</option><option value="1">лише з e-mail</option>
   <option value="0">без e-mail (треба знайти)</option>
   <option value="m">лише з поштою мера</option></select>
  <select id="pop"><option value="0">будь-який розмір</option><option value="30000">від 30 тис. мешканців</option>
   <option value="100000">від 100 тис.</option><option value="300000">від 300 тис.</option></select>
 </div>
 <table><thead><tr><th>бал</th><th>місто</th><th>країна</th><th>мешканців</th><th>мова</th>
   <th>e-mail</th><th>мер</th><th>пошта мера</th><th>телефон</th><th>сайт</th>
   <th>примітка</th></tr></thead>
  <tbody id="rows"></tbody></table>
</div>
<footer>__FOOTER__</footer>
<script>
const P = __PARTNERS__, CN = __COUNTRY_NAMES__;
const esc = s => (s||'').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const cls = p => p >= 7 ? 'hot' : (p >= 4 ? 'warm' : 'cold');
function draw(){
  const q = document.getElementById('q').value.toLowerCase();
  const cc = document.getElementById('country').value;
  const mf = document.getElementById('mail').value;
  const pf = parseInt(document.getElementById('pop').value, 10);
  const rows = P.filter(r =>
    (!cc || r.country === cc) &&
    (mf === '' || (mf === 'm' ? !!r.mayor_email : (mf === '1' ? !!r.email : !r.email))) &&
    (r.population || 0) >= pf &&
    (!q || (r.name + ' ' + (r.email||'') + ' ' + (r.mayor||'') + ' ' + (r.mayor_email||'') + ' ' + (r.admin||'') + ' ' + (r.note||'')).toLowerCase().includes(q)));
  document.getElementById('rows').innerHTML = rows.map(r => `
    <tr><td><span class="pri ${cls(r.priority)}">${r.priority}</span></td>
    <td><b>${esc(r.name)}</b>${r.admin ? '<div class="badge">' + esc(r.admin) + '</div>' : ''}</td>
    <td>${esc(CN[r.country] || r.country)}</td>
    <td>${r.population ? r.population.toLocaleString('uk-UA') : '—'}</td>
    <td>${r.lang}</td>
    <td>${r.email ? '<a href="mailto:' + esc(r.email) + '?subject=' + encodeURIComponent(r.subject) + '">' + esc(r.email) + '</a>' : '<span class="badge">немає</span>'}</td>
    <td>${r.mayor ? esc(r.mayor) : '—'}</td>
    <td>${r.mayor_email ? '<a href="mailto:' + esc(r.mayor_email) + '?subject=' + encodeURIComponent(r.subject) + '">' + esc(r.mayor_email) + '</a>' : '—'}</td>
    <td>${r.phone ? esc(r.phone) : '—'}</td>
    <td>${r.site ? '<a href="' + esc(r.site) + '" target="_blank" rel="noopener">сайт</a>' : '—'}</td>
    <td>${esc(r.note || '')}</td></tr>`).join('');
  const counts = {};
  rows.forEach(r => counts[r.country] = (counts[r.country] || 0) + 1);
  const boxes = [`<div class="stat"><b>${rows.length}</b><span>міст у вибірці</span></div>`,
    `<div class="stat"><b style="color:#5fd39a">${rows.filter(r => r.email).length}</b><span>з e-mail</span></div>`,
    `<div class="stat"><b style="color:#f6cf7a">${rows.filter(r => r.mayor_email).length}</b><span>з поштою мера</span></div>`];
  Object.keys(counts).sort((a,b) => counts[b]-counts[a]).forEach(c =>
    boxes.push(`<div class="stat"><b>${counts[c]}</b><span>${esc(CN[c] || c)}</span></div>`));
  document.getElementById('stats').innerHTML = boxes.join('');
}
['q','country','mail','pop'].forEach(id => document.getElementById(id).addEventListener('input', draw));
draw();
</script></body></html>
"""

NAV_PAGES = [("index.html", "← стрічка грантів"), ("donors.html", "📇 реєстр донорів"),
             ("danube.html", "🌊 Дунай"), ("cities_big.html", "🏙 великі громади"),
             ("cities_green.html", "🌱 зелені")]


def _nav(current: str) -> str:
    return "".join(
        f'<a href="{href}"{" class=\"on\"" if href == current else ""}>{label}</a>'
        for href, label in NAV_PAGES)


def _channel_rows(db: Database, donors_list: list[dict]) -> list[dict]:
    """Рядки для сторінки каналу з карток реєстру донорів."""
    rows = []
    for d in donors_list:
        parts = [x for x in (d.get("notes") or "").split(" · ") if x]
        pop_part = next((x for x in parts if "мешканців" in x), "")
        mayor_part = next((x for x in parts if x.startswith("мер: ")), "")
        mail_part = next((x for x in parts if x.startswith("пошта мера: ")), "")
        population = int(re.sub(r"\D", "", pop_part) or 0) if pop_part else 0
        admin = parts[0] if parts and parts[0] != pop_part else ""
        note = " · ".join(x for x in parts
                          if x not in (admin, pop_part, mayor_part, mail_part))
        rows.append({
            "name": d.get("name", ""), "country": d.get("country", ""),
            "lang": d.get("lang", "en"), "email": d.get("contact_email", ""),
            "phone": d.get("contact_phone", ""), "site": d.get("site", ""),
            "priority": d.get("priority", 0), "admin": admin,
            "population": population, "note": note,
            "mayor": mayor_part[5:] if mayor_part else "",
            "mayor_email": mail_part[12:] if mail_part else "",
            "subject": _subject_for(d.get("lang", "en")),
        })
    return rows


def _write_channel_page(rows: list[dict], *, page: str, title: str, sub: str,
                        hint: str, footer: str, out_dir: Path) -> Path:
    from . import donors as donors_mod

    codes = sorted({r["country"] for r in rows})
    options = "".join(
        f'<option value="{c}">{donors_mod.COUNTRY_NAME.get(c, c)}</option>'
        for c in codes)
    org = config.load_profile().get("community", {})
    html = (CHANNEL_HTML
            .replace("__PARTNERS__", json.dumps(rows, ensure_ascii=False))
            .replace("__COUNTRY_NAMES__", json.dumps(donors_mod.COUNTRY_NAME,
                                                     ensure_ascii=False))
            .replace("__COUNTRY_OPTIONS__", options)
            .replace("__NAV__", _nav(page))
            .replace("__TITLE__", title).replace("__SUB__", sub)
            .replace("__HINT__", hint).replace("__FOOTER__", footer)
            .replace("__ORG__", f"{org.get('name_uk', '')} · {org.get('region_uk', '')}")
            .replace("__UPDATED__", datetime.now().strftime("%d.%m.%Y %H:%M")))
    path = out_dir / page
    path.write_text(html, encoding="utf-8")
    (out_dir / page.replace(".html", ".json")).write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def export_danube(db: Database, out_dir: Path | None = None) -> Path:
    """Сторінка каналу «Дунайський басейн»."""
    from . import danube as danube_mod

    out_dir = Path(out_dir or config.DOCS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _channel_rows(db, danube_mod.list_donors(db))
    hint = ("Аргумент листа: наша громада стоїть на <b>Тисі — найбільшій притоці "
            "Дунаю</b>, і відходи, не зібрані у верхів'ї, за кілька днів опиняються "
            "нижче за течією. Наведення ладу з ТПВ у Вилоцькій громаді напряму "
            "зменшує забруднення спільного басейну — це мова Рамкової водної "
            "директиви ЄС, ICPDR та стратегії EUSDR. Перелік громад і контактів — "
            "у <code>config/danube_partners.yaml</code>, список розсилки — "
            "<code>data/danube_mailing.csv</code>.")
    return _write_channel_page(
        rows, page="danube.html",
        title="🌊 Придунайські громади: Австрія · Угорщина · Румунія",
        sub="спільний річковий басейн Тиса → Дунай", hint=hint,
        footer=("Оновлення: <code>python scripts/fetch_danube_partners.py</code> → "
                "<code>python -m grant_radar danube</code> · розсилка: "
                "<code>data/danube_mailing.csv</code>"),
        out_dir=out_dir)


def export_cities(db: Database, channel: str, out_dir: Path | None = None) -> Path:
    """Сторінка каналів «великі громади» та «зелені»."""
    from . import cities as cities_mod

    meta = cities_mod.CHANNELS[channel]
    out_dir = Path(out_dir or config.DOCS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _channel_rows(db, cities_mod.list_donors(db, channel))
    return _write_channel_page(
        rows, page=meta["page"], title=meta["title"], sub=meta["sub"],
        hint=meta["hint"], footer=meta["footer"], out_dir=out_dir)


_SUBJECTS = {
    "it": "Proposta di partenariato – comunità di Vylok, Transcarpazia, Ucraina",
    "hu": "Együttműködési kezdeményezés – Tiszaújlak (Vylok), Kárpátalja",
    "de": "Kooperationsanfrage – Gemeinde Vylok, Transkarpatien, Ukraine",
    "ro": "Propunere de parteneriat – comunitatea Vylok, Transcarpatia, Ucraina",
    "pl": "Propozycja współpracy – gmina Wyłok, Zakarpacie, Ukraina",
    "en": "Partnership request – Vylok hromada, Zakarpattia, Ukraine",
    "uk": "Пропозиція співпраці — Вилоцька громада, Закарпаття",
}


def _subject_for(lang: str) -> str:
    return _SUBJECTS.get(lang, _SUBJECTS["en"])
