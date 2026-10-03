"""Головний цикл агента: збір → нормалізація → скоринг → LLM → збереження."""
from __future__ import annotations

import logging
from typing import Any

from . import config
from .classify import classify
from .collectors import eu_sedia, rss, ted, worldbank
from .db import Database, now_iso
from .llm import LLMAnalyzer
from .models import Opportunity
from .scoring import Scorer

log = logging.getLogger(__name__)

COLLECTORS = {"sedia": eu_sedia.collect, "rss": rss.collect,
              "ted": ted.collect, "worldbank": worldbank.collect}


def run(db: Database | None = None, use_llm: bool = True) -> dict[str, Any]:
    started = now_iso()
    profile = config.load_profile()
    sources = config.load_sources()
    scorer = Scorer(profile)
    db = db or Database(config.DB_PATH)
    errors: list[str] = []

    collected: list[tuple[Opportunity, float]] = []
    hints = {s["id"]: s.get("beneficiary_hint") for s in sources if s.get("beneficiary_hint")}
    for src in sources:
        fn = COLLECTORS.get(src.get("type", "rss"))
        if not fn:
            errors.append(f"{src['id']}: невідомий тип {src.get('type')}")
            continue
        try:
            items = fn(src)
            log.info("  %-22s %3d записів", src["id"], len(items))
            collected += [(o, float(src.get("weight", 1.0))) for o in items]
        except Exception as exc:
            msg = f"{src['id']}: {exc}"
            log.warning("  %s", msg)
            errors.append(msg)

    # дедуплікація за uid (одна й та сама новина у двох стрічках)
    unique: dict[str, tuple[Opportunity, float]] = {}
    for opp, weight in collected:
        if opp.uid not in unique:
            unique[opp.uid] = (opp, weight)

    new_count = 0
    scored: list[Opportunity] = []
    for opp, weight in unique.values():
        opp.score, opp.band, reasons = scorer.score(opp, weight)
        opp.reasons = "; ".join(reasons)
        opp.beneficiary, opp.beneficiary_why = classify(opp.title, opp.summary, opp.programme)
        hint = hints.get(opp.source_id)
        if opp.beneficiary == "unknown" and hint:
            opp.beneficiary, opp.beneficiary_why = hint, "за типом джерела"
        scored.append(opp)

    # ── LLM-шар: лише для перспективних записів, яких ще немає в базі з аналізом
    cfg = profile.get("scoring", {})
    analyzer = LLMAnalyzer(config.profile_text(profile))
    if use_llm and analyzer.enabled:
        candidates = [o for o in scored if o.score >= int(cfg.get("llm_min_score", 30))]
        candidates.sort(key=lambda o: o.score, reverse=True)
        budget = int(cfg.get("llm_max_items", 25))
        done = 0
        for opp in candidates:
            if done >= budget:
                break
            existing = db.get(opp.uid)
            if existing and existing.get("llm_summary"):
                continue  # вже проаналізовано раніше — не платимо двічі
            res = analyzer.analyze(opp)
            done += 1
            if not res:
                continue
            opp.llm_score = int(res.get("score") or 0)
            opp.llm_summary = str(res.get("summary_uk") or "")
            fit = str(res.get("fit_uk") or "")
            if res.get("eligible") is False:
                fit = "⚠️ КП, імовірно, не може бути заявником. " + fit
            opp.llm_fit = fit
            opp.llm_actions = str(res.get("actions_uk") or "")
            benef = str(res.get("beneficiary") or "").strip()
            if benef in ("communal", "private", "both"):
                opp.beneficiary = benef
                opp.beneficiary_why = (opp.beneficiary_why + " | уточнено AI").strip(" |")
            # підсумковий бал: правила 60% + LLM 40%
            opp.score = int(round(opp.score * 0.6 + opp.llm_score * 0.4))
            opp.band = scorer.band(opp.score)
        log.info("  LLM проаналізував %d записів (модель %s)", done, analyzer.model)
    elif use_llm:
        log.info("  LLM вимкнено (немає OPENAI_API_KEY) — працюють лише правила")

    for opp in scored:
        if db.upsert(opp):
            new_count += 1

    db.log_run(started, len(scored), new_count, errors)
    stats = {"collected": len(scored), "new": new_count, "errors": errors,
             "llm": analyzer.enabled and use_llm}
    log.info("Готово: %d записів, %d нових, помилок: %d",
             len(scored), new_count, len(errors))
    return stats


def rescore(db: Database | None = None) -> int:
    """Перерахувати бали для всієї бази після зміни config/profile.yaml (без мережі)."""
    profile = config.load_profile()
    scorer = Scorer(profile)
    sources = config.load_sources()
    weights = {s["id"]: float(s.get("weight", 1.0)) for s in sources}
    hints = {s["id"]: s.get("beneficiary_hint") for s in sources if s.get("beneficiary_hint")}
    db = db or Database(config.DB_PATH)
    rows = [dict(r) for r in db.conn.execute("SELECT * FROM opportunities")]
    for r in rows:
        opp = Opportunity(
            source_id=r["source_id"], source_name=r["source_name"], region=r["region"],
            title=r["title"], url=r["url"], summary=r["summary"] or "",
            programme=r["programme"] or "", identifier=r["identifier"] or "",
            status=r["status"] or "", published_at=r["published_at"],
            deadline_at=r["deadline_at"],
        )
        score, band, reasons = scorer.score(opp, weights.get(r["source_id"], 1.0))
        benef, benef_why = classify(opp.title, opp.summary, opp.programme)
        if benef == "unknown" and hints.get(r["source_id"]):
            benef, benef_why = hints[r["source_id"]], "за типом джерела"
        db.conn.execute(
            "UPDATE opportunities SET score=?, band=?, reasons=?, beneficiary=?, "
            "beneficiary_why=? WHERE uid=?",
            (score, band, "; ".join(reasons), benef, benef_why, r["uid"]),
        )
    db.conn.commit()
    log.info("Перераховано %d записів", len(rows))
    return len(rows)
