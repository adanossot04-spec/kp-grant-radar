"""Статичний експорт для GitHub Pages: docs/index.html + docs/data.json.

Сторінка самодостатня (CSS та JS вбудовані, фільтрація на клієнті),
тому працює на Pages без жодного сервера.
"""
from __future__ import annotations

import json
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
  <button class="tab" data-feed="all">🌍 Усе разом <b id="cnt_all">0</b></button>
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

// вкладки: 🇺🇦 пряме фінансування / 🇪🇺 консорціуми ЄС / усе разом
window.FEED="ua";
document.getElementById("cnt_ua").textContent  = DATA.filter(d=>(d.feed||"ua")==="ua").length;
document.getElementById("cnt_eu").textContent  = DATA.filter(d=>(d.feed||"ua")==="eu").length;
document.getElementById("cnt_all").textContent = DATA.length;
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
    path = out_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path
