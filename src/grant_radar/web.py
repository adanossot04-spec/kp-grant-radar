"""Веб-дашборд (FastAPI + Jinja2). Запуск: python -m grant_radar serve"""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import config
from .db import Database
from . import tracks as tracks_mod
from . import budget as budget_mod
from .classify import LABEL as BENEF_LABEL
from .scoring import BAND_LABEL
from .screening import REASON_TEXT

app = FastAPI(title="Грант-радар КП", docs_url="/api/docs")
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))
db = Database(config.DB_PATH)

STATUS_LABEL = {"open": "конкурс відкрито", "forthcoming": "анонсовано", "closed": "закрито"}
USER_LABEL = {"interesting": "⭐ цікаво", "in_progress": "✍️ готуємо заявку",
              "submitted": "📨 подано", "rejected": "відмова", "ignored": "🗑 не актуально"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: str = "", band: str = "", region: str = "",
          source: str = "", status: str = "", order: str = "score", all: str = "",
          benef: str = "", group: str = "track", track: str = "", equip: str = "",
          budget: str = "", apply: str = "", hidden: str = "", feed: str = "ua"):
    items = db.query(
        search=q or None, band=band or None, region=region or None,
        source_id=source or None, user_status=status or None,
        beneficiary=benef or None, track=track or None,
        equipment_only=bool(equip), budget_band=budget or None,
        apply_only=bool(apply), include_hidden=bool(hidden),
        feed=None if feed == "all" else feed, order=order,
        only_active=not bool(all), limit=400,
    )
    # групування підсумкового списку
    groups: list[tuple[str, list]] = []
    if group == "track" and not track:
        buckets: dict[str, list] = {}
        for it in items:
            buckets.setdefault(it.get("track") or "other", []).append(it)
        for key in tracks_mod.ordered_tracks(list(buckets)):
            groups.append((tracks_mod.LABEL.get(key, key), buckets[key]))
    elif group == "benef" and not benef:
        buckets = {"communal": [], "both": [], "private": [], "unknown": []}
        for it in items:
            buckets.setdefault(it.get("beneficiary") or "unknown", buckets["unknown"]).append(it)
        for key in ("communal", "both", "private", "unknown"):
            if buckets[key]:
                groups.append((BENEF_LABEL[key], buckets[key]))
    else:
        groups = [("", items)]
    profile = config.load_profile()
    stats = db.stats()
    last = stats.get("last_run") or {}
    qs = urlencode({k: v for k, v in
                    {"q": q, "band": band, "region": region, "source": source,
                     "status": status, "order": order, "all": all,
                     "benef": benef, "group": group, "track": track,
                     "equip": equip, "budget": budget, "apply": apply,
                     "hidden": hidden, "feed": feed}.items() if v})
    return templates.TemplateResponse(request, "dashboard.html", {
        "items": items, "stats": stats,
        "org": profile.get("organization", {}),
        "sources": db.sources_in_db(),
        "band_label": BAND_LABEL, "status_label": STATUS_LABEL, "user_label": USER_LABEL,
        "hide_reason_label": REASON_TEXT,
        "groups": groups, "benef_label": BENEF_LABEL,
        "track_label": tracks_mod.LABEL, "track_short": tracks_mod.SHORT,
        "tracks": tracks_mod.ordered_tracks(db.tracks_in_db()),
        "budget_label": budget_mod.BAND_LABEL, "budget_short": budget_mod.BAND_SHORT,
        "budget_bands": [b for b in budget_mod.BAND_ORDER if b in db.budget_bands_in_db()],
        "budget_human": budget_mod.human,
        "f": {"q": q, "band": band, "region": region, "source": source,
              "status": status, "order": order, "all": all, "benef": benef,
              "group": group, "track": track, "equip": equip, "budget": budget,
              "apply": apply, "hidden": hidden, "feed": feed},
        "qs": qs,
        "donor_total": db.donor_count(),
        "qs_without_feed": urlencode({k: v for k, v in
                                      {"q": q, "band": band, "region": region,
                                       "source": source, "status": status, "order": order,
                                       "all": all, "benef": benef, "group": group,
                                       "track": track, "equip": equip, "budget": budget,
                                       "apply": apply, "hidden": hidden}.items() if v}),
        "last_run": (last.get("finished_at") or "—")[:16].replace("T", " "),
    })


@app.get("/mark/{uid}")
def mark(request: Request, uid: str, status: str = "interesting"):
    db.set_user_status(uid, status)
    # повертаємось на ту саму сторінку з тими самими фільтрами
    keep = {k: v for k, v in request.query_params.items() if k != "status"}
    return RedirectResponse("/?" + urlencode(keep) if keep else "/", status_code=303)


# ───────────────────────────── JSON API ─────────────────────────────
@app.get("/api/opportunities")
def api_items(min_score: int = 0, band: str = "", region: str = "",
              beneficiary: str = "", track: str = "", equipment: bool = False,
              budget: str = "", apply: bool = False, hidden: bool = False,
              order: str = "score", limit: int = 100):
    return JSONResponse(db.query(min_score=min_score, band=band or None,
                                 region=region or None,
                                 beneficiary=beneficiary or None,
                                 track=track or None, equipment_only=equipment,
                                 budget_band=budget or None, apply_only=apply,
                                 include_hidden=hidden, order=order,
                                 limit=limit))


@app.get("/api/draft/{uid}")
def api_draft(uid: str, org: str = ""):
    """Згенерувати чернетку заявки за даними з config/memory.yaml."""
    from .draft import build
    path = build(uid, db=db, org_id=org or None)
    return JSONResponse({"file": str(path), "text": path.read_text(encoding="utf-8")})


@app.get("/api/stats")
def api_stats():
    return JSONResponse(db.stats())


@app.post("/api/collect")
def api_collect():
    from .pipeline import run
    return JSONResponse(run(db=db))

# ───────────────────── реєстр донорів (вкладка 🤝) ─────────────────────
@app.get("/donors", response_class=HTMLResponse)
def donors_page(request: Request, q: str = "", circle: str = "", goods: str = "",
                country: str = "", status: str = "", minp: int = 0):
    from . import donors as donors_mod
    rows = db.donors(search=q or None, circle=int(circle) if circle else None,
                     goods=goods or None, country=country or None,
                     status=status or None, min_priority=minp or None, limit=1000)
    return templates.TemplateResponse(request, "donors.html", {
        "donors": rows,
        "dstats": db.donor_stats(),
        "community": config.load_profile().get("community", {}),
        "circles": donors_mod.CIRCLE_LABEL,
        "goods_labels": donors_mod.GOODS_LABEL,
        "org_labels": donors_mod.ORG_LABEL,
        "status_labels": donors_mod.STATUS_LABEL,
        "country_names": donors_mod.COUNTRY_NAME,
        "f": {"q": q, "circle": circle, "goods": goods, "country": country,
              "status": status, "minp": minp},
    })


@app.get("/donors/{donor_id}/letter", response_class=HTMLResponse)
def donor_letter(donor_id: int, lang: str = ""):
    """Готовий лист-запит до донора мовою його країни."""
    from html import escape

    from . import donors as donors_mod
    d = db.donor(donor_id)
    if not d:
        return HTMLResponse("<h3>Донора не знайдено</h3>", status_code=404)
    text = donors_mod.build_letter(d, lang=lang or None)
    langs = "".join(
        f'<a href="/donors/{donor_id}/letter?lang={code}" '
        f'style="margin-right:10px">{label}</a>'
        for code, label in [("hu", "угорською"), ("de", "німецькою"),
                            ("pl", "польською"), ("en", "англійською"),
                            ("uk", "українською")])
    return HTMLResponse(
        "<html><head><meta charset='utf-8'><title>Лист донору</title></head>"
        "<body style='background:#0f1115;color:#e8eaef;font:15px/1.6 system-ui;padding:26px'>"
        f"<div style='margin-bottom:14px'>Мова листа: {langs}</div>"
        "<textarea style='width:100%;height:75vh;background:#171a21;color:#e8eaef;"
        "border:1px solid #2a2f3a;border-radius:12px;padding:16px;font:14px/1.6 ui-monospace,"
        f"Menlo,Consolas,monospace'>{escape(text)}</textarea>"
        "<p style='color:#9aa3b2'>Скопіюйте текст, перевірте контактні дані "
        "(вони беруться з <code>config/profile.yaml</code> → <code>community.contact</code>) "
        "і надішліть. Після надсилання позначте донора як «📨 надіслано».</p>"
        "</body></html>")


@app.get("/donors/{donor_id}/status")
def donor_status(donor_id: int, value: str = "letter_sent"):
    from datetime import date, timedelta

    fields: dict[str, object] = {"status": value}
    if value == "letter_sent":
        today = date.today()
        fields["letter_sent_at"] = today.isoformat()
        fields["followup_at"] = (today + timedelta(days=21)).isoformat()
    db.set_donor(donor_id, **fields)
    return RedirectResponse("/donors", status_code=303)


@app.get("/api/donors")
def api_donors(min_priority: int = 0, limit: int = 500):
    return JSONResponse(db.donors(min_priority=min_priority or None, limit=limit))
