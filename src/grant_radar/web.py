"""Веб-дашборд (FastAPI + Jinja2). Запуск: python -m grant_radar serve"""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import config
from .db import Database
from .classify import LABEL as BENEF_LABEL
from .scoring import BAND_LABEL

app = FastAPI(title="Грант-радар КП", docs_url="/api/docs")
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))
db = Database(config.DB_PATH)

STATUS_LABEL = {"open": "конкурс відкрито", "forthcoming": "анонсовано", "closed": "закрито"}
USER_LABEL = {"interesting": "⭐ цікаво", "in_progress": "✍️ готуємо заявку",
              "submitted": "📨 подано", "rejected": "відмова", "ignored": "🗑 не актуально"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, q: str = "", band: str = "", region: str = "",
          source: str = "", status: str = "", order: str = "score", all: str = "",
          benef: str = "", group: str = "1"):
    items = db.query(
        search=q or None, band=band or None, region=region or None,
        source_id=source or None, user_status=status or None,
        beneficiary=benef or None, order=order, only_active=not bool(all), limit=400,
    )
    # групування: окремо комунальні, окремо приватні, окремо спільні
    groups: list[tuple[str, list]] = []
    if group == "1" and not benef:
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
                     "benef": benef, "group": group}.items() if v})
    return templates.TemplateResponse(request, "dashboard.html", {
        "items": items, "stats": stats,
        "org": profile.get("organization", {}),
        "sources": db.sources_in_db(),
        "band_label": BAND_LABEL, "status_label": STATUS_LABEL, "user_label": USER_LABEL,
        "groups": groups, "benef_label": BENEF_LABEL,
        "f": {"q": q, "band": band, "region": region, "source": source,
              "status": status, "order": order, "all": all, "benef": benef,
              "group": group},
        "qs": qs,
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
              beneficiary: str = "", limit: int = 100):
    return JSONResponse(db.query(min_score=min_score, band=band or None,
                                 region=region or None,
                                 beneficiary=beneficiary or None, limit=limit))


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
