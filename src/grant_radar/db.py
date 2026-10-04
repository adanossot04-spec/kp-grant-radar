"""Сховище SQLite: історія можливостей + робочий статус КП."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import Opportunity

SCHEMA = """
CREATE TABLE IF NOT EXISTS donors (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    uid            TEXT UNIQUE,        -- запис стрічки 🤝, з якого взято донора
    name           TEXT NOT NULL,
    country        TEXT DEFAULT '??',
    org_type       TEXT DEFAULT 'municipality',
    circle         INTEGER DEFAULT 4,  -- коло близькості 1–5
    goods          TEXT DEFAULT 'other',
    what           TEXT,               -- що саме передавав (привід для листа)
    recipient      TEXT,               -- кому передавав
    event_date     TEXT,
    news_url       TEXT,
    site           TEXT DEFAULT '',
    contact_person TEXT DEFAULT '',
    contact_email  TEXT DEFAULT '',
    contact_phone  TEXT DEFAULT '',
    lang           TEXT DEFAULT 'en',
    proven         INTEGER DEFAULT 0,  -- Д
    bridge         INTEGER DEFAULT 0,  -- М
    need           INTEGER DEFAULT 0,  -- З
    cost           INTEGER DEFAULT 0,  -- В
    priority       INTEGER DEFAULT 0,  -- Д + М + З − В
    status         TEXT DEFAULT 'new',
    letter_sent_at TEXT,
    followup_at    TEXT,
    notes          TEXT DEFAULT '',
    created_at     TEXT,
    updated_at     TEXT
);

CREATE TABLE IF NOT EXISTS opportunities (
    uid           TEXT PRIMARY KEY,
    source_id     TEXT,
    source_name   TEXT,
    region        TEXT,
    title         TEXT,
    url           TEXT,
    summary       TEXT,
    programme     TEXT,
    identifier    TEXT,
    status        TEXT,
    published_at  TEXT,
    deadline_at   TEXT,
    budget        TEXT,
    score         INTEGER DEFAULT 0,
    band          TEXT,
    reasons       TEXT,
    beneficiary   TEXT DEFAULT 'unknown',
    beneficiary_why TEXT,
    track         TEXT DEFAULT 'other',
    equipment     INTEGER DEFAULT 0,
    budget_eur    INTEGER,
    budget_band   TEXT DEFAULT 'unknown',
    apply_url     TEXT DEFAULT '',
    apply_host    TEXT DEFAULT '',
    apply_label   TEXT DEFAULT '',
    article_url   TEXT DEFAULT '',
    resolved_at   TEXT,
    actionable    INTEGER DEFAULT 1,   -- 0 = новина/протерміноване, у стрічці не показуємо
    hide_reason   TEXT DEFAULT '',
    feed          TEXT DEFAULT 'ua',   -- ua = пряме фінансування, eu = консорціум ЄС,
                                     -- aid = побратими й передача техніки
    llm_score     INTEGER,
    llm_summary   TEXT,
    llm_fit       TEXT,
    llm_actions   TEXT,
    raw_json      TEXT,
    first_seen    TEXT,
    last_seen     TEXT,
    notified      INTEGER DEFAULT 0,
    user_status   TEXT DEFAULT 'new',   -- new | interesting | in_progress | submitted | rejected | ignored
    user_note     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    finished_at TEXT,
    collected  INTEGER,
    new_items  INTEGER,
    errors     TEXT
);
"""


INDEXES = """CREATE INDEX IF NOT EXISTS idx_opp_score    ON opportunities(score DESC);
CREATE INDEX IF NOT EXISTS idx_opp_deadline ON opportunities(deadline_at);
CREATE INDEX IF NOT EXISTS idx_opp_source   ON opportunities(source_id);
CREATE INDEX IF NOT EXISTS idx_opp_benef    ON opportunities(beneficiary);
CREATE INDEX IF NOT EXISTS idx_opp_track    ON opportunities(track);
CREATE INDEX IF NOT EXISTS idx_opp_budget   ON opportunities(budget_band);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.executescript(INDEXES)
        self.conn.commit()

    def _migrate(self) -> None:
        """Додає нові колонки до вже наявної бази (сумісність зі старими версіями)."""
        have = {r[1] for r in self.conn.execute("PRAGMA table_info(opportunities)")}
        for col, ddl in (("beneficiary", "TEXT DEFAULT 'unknown'"),
                         ("beneficiary_why", "TEXT"),
                         ("track", "TEXT DEFAULT 'other'"),
                         ("equipment", "INTEGER DEFAULT 0"),
                         ("budget_eur", "INTEGER"),
                         ("budget_band", "TEXT DEFAULT 'unknown'"),
                         ("apply_url", "TEXT DEFAULT ''"),
                         ("apply_host", "TEXT DEFAULT ''"),
                         ("apply_label", "TEXT DEFAULT ''"),
                         ("article_url", "TEXT DEFAULT ''"),
                         ("resolved_at", "TEXT"),
                         ("actionable", "INTEGER DEFAULT 1"),
                         ("hide_reason", "TEXT DEFAULT ''"),
                         ("feed", "TEXT DEFAULT 'ua'")):
            if col not in have:
                self.conn.execute(f"ALTER TABLE opportunities ADD COLUMN {col} {ddl}")

    # ─────────────────────────── запис ───────────────────────────
    def upsert(self, opp: Opportunity) -> bool:
        """Повертає True, якщо запис новий."""
        cur = self.conn.execute("SELECT uid FROM opportunities WHERE uid = ?", (opp.uid,))
        exists = cur.fetchone() is not None
        ts = now_iso()
        payload = {
            "uid": opp.uid,
            "source_id": opp.source_id,
            "source_name": opp.source_name,
            "region": opp.region,
            "title": opp.title,
            "url": opp.url,
            "summary": opp.summary,
            "programme": opp.programme,
            "identifier": opp.identifier,
            "status": opp.status,
            "published_at": opp.published_at,
            "deadline_at": opp.deadline_at,
            "budget": opp.budget,
            "score": opp.score,
            "band": opp.band,
            "reasons": opp.reasons,
            "beneficiary": opp.beneficiary,
            "beneficiary_why": opp.beneficiary_why,
            "track": opp.track,
            "equipment": opp.equipment,
            "budget_eur": opp.budget_eur,
            "budget_band": opp.budget_band,
            "llm_score": opp.llm_score,
            "llm_summary": opp.llm_summary,
            "llm_fit": opp.llm_fit,
            "llm_actions": opp.llm_actions,
            "raw_json": json.dumps(opp.raw, ensure_ascii=False)[:200000],
            "last_seen": ts,
        }
        if exists:
            sets = ", ".join(f"{k} = :{k}" for k in payload if k != "uid")
            # не затираємо LLM-поля порожнечею
            if not opp.llm_summary:
                for k in ("llm_score", "llm_summary", "llm_fit", "llm_actions"):
                    payload.pop(k)
                sets = ", ".join(f"{k} = :{k}" for k in payload if k != "uid")
            self.conn.execute(f"UPDATE opportunities SET {sets} WHERE uid = :uid", payload)
        else:
            payload["first_seen"] = ts
            cols = ", ".join(payload)
            vals = ", ".join(f":{k}" for k in payload)
            self.conn.execute(f"INSERT INTO opportunities ({cols}) VALUES ({vals})", payload)
        self.conn.commit()
        return not exists

    def log_run(self, started: str, collected: int, new_items: int, errors: list[str]) -> None:
        self.conn.execute(
            "INSERT INTO runs (started_at, finished_at, collected, new_items, errors) VALUES (?,?,?,?,?)",
            (started, now_iso(), collected, new_items, json.dumps(errors, ensure_ascii=False)),
        )
        self.conn.commit()

    def set_user_status(self, uid: str, status: str, note: str | None = None) -> None:
        if note is None:
            self.conn.execute("UPDATE opportunities SET user_status=? WHERE uid=?", (status, uid))
        else:
            self.conn.execute(
                "UPDATE opportunities SET user_status=?, user_note=? WHERE uid=?", (status, note, uid)
            )
        self.conn.commit()

    def mark_notified(self, uids: Iterable[str]) -> None:
        self.conn.executemany(
            "UPDATE opportunities SET notified=1 WHERE uid=?", [(u,) for u in uids]
        )
        self.conn.commit()

    # ─────────────────────────── читання ───────────────────────────
    def query(
        self,
        *,
        min_score: int = 0,
        region: str | None = None,
        source_id: str | None = None,
        band: str | None = None,
        beneficiary: str | None = None,
        track: str | None = None,
        equipment_only: bool = False,
        budget_band: str | None = None,
        apply_only: bool = False,
        include_hidden: bool = False,
        feed: str | None = None,
        user_status: str | None = None,
        search: str | None = None,
        only_active: bool = True,
        days_left_max: int | None = None,
        order: str = "score",
        limit: int = 300,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM opportunities WHERE score >= ?"
        args: list[Any] = [min_score]
        if region:
            sql += " AND region = ?"
            args.append(region)
        if source_id:
            sql += " AND source_id = ?"
            args.append(source_id)
        if band:
            sql += " AND band = ?"
            args.append(band)
        if beneficiary:
            if beneficiary in ("communal", "private"):
                sql += " AND beneficiary IN (?, 'both')"
                args.append(beneficiary)
            else:
                sql += " AND beneficiary = ?"
                args.append(beneficiary)
        if track:
            sql += " AND track = ?"
            args.append(track)
        if equipment_only:
            sql += " AND equipment = 1"
        if apply_only:
            sql += " AND apply_url IS NOT NULL AND apply_url <> ''"
        if not include_hidden:
            sql += " AND COALESCE(actionable, 1) = 1"
        if feed in ("ua", "eu", "aid", "edu"):
            sql += " AND COALESCE(feed, 'ua') = ?"
            args.append(feed)
        if budget_band:
            sql += " AND COALESCE(budget_band, 'unknown') = ?"
            args.append(budget_band)
        if user_status:
            sql += " AND user_status = ?"
            args.append(user_status)
        if search:
            sql += " AND (lower(title) LIKE ? OR lower(summary) LIKE ?)"
            like = f"%{search.lower()}%"
            args += [like, like]
        if only_active:
            sql += " AND (deadline_at IS NULL OR deadline_at = '' OR deadline_at >= ?)"
            args.append(datetime.now(timezone.utc).isoformat(timespec="seconds"))
        orders = {
            "score": "score DESC, deadline_at IS NULL, deadline_at ASC",
            "deadline": "deadline_at IS NULL, deadline_at ASC, score DESC",
            "newest": "first_seen DESC, score DESC",
            "budget": "budget_eur IS NULL, budget_eur DESC, score DESC",
            "budget_asc": "budget_eur IS NULL, budget_eur ASC, score DESC",
        }
        sql += f" ORDER BY {orders.get(order, orders['score'])} LIMIT ?"
        args.append(limit)
        rows = [dict(r) for r in self.conn.execute(sql, args)]
        if days_left_max is not None:
            rows = [r for r in rows if (_days_left(r["deadline_at"]) or 10**6) <= days_left_max]
        for r in rows:
            r["days_left"] = _days_left(r["deadline_at"])
        return rows

    def get(self, uid: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM opportunities WHERE uid=?", (uid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["days_left"] = _days_left(d["deadline_at"])
        return d

    def unnotified(self, min_score: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM opportunities WHERE notified = 0 AND score >= ? "
            "AND COALESCE(actionable, 1) = 1 "
            "AND (deadline_at IS NULL OR deadline_at = '' OR deadline_at >= date('now')) "
            "ORDER BY score DESC LIMIT 50",
            (min_score,),
        )
        out = [dict(r) for r in rows]
        for r in out:
            r["days_left"] = _days_left(r["deadline_at"])
        return out

    # ───────────────────── реєстр донорів (вкладка 🤝) ─────────────────────
    def add_donor(self, card: dict[str, Any]) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fields = ["uid", "name", "country", "org_type", "circle", "goods", "what",
                  "recipient", "event_date", "news_url", "site", "contact_person",
                  "contact_email", "contact_phone", "lang", "proven", "bridge",
                  "need", "cost", "priority", "status", "notes"]
        values = [card.get(f) for f in fields]
        cur = self.conn.execute(
            f"INSERT OR IGNORE INTO donors ({', '.join(fields)}, created_at, updated_at) "
            f"VALUES ({', '.join('?' * len(fields))}, ?, ?)", (*values, now, now))
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def update_donor_scores(self, card: dict[str, Any]) -> None:
        """Оновлює лише автоматичні поля; ручні правки користувача не чіпає."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE donors SET name=CASE WHEN name='—' THEN ? ELSE name END, "
            "country=?, org_type=?, circle=?, goods=?, what=?, recipient=?, "
            "event_date=?, news_url=?, proven=?, bridge=?, need=?, cost=?, "
            "priority=?, updated_at=? WHERE uid=?",
            (card["name"], card["country"], card["org_type"], card["circle"],
             card["goods"], card["what"], card["recipient"], card["event_date"],
             card["news_url"], card["proven"], card["bridge"], card["need"],
             card["cost"], card["priority"], now, card["uid"]))
        self.conn.commit()

    def donor_by_uid(self, uid: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM donors WHERE uid = ?", (uid,)).fetchone()
        return dict(row) if row else None

    def donor(self, donor_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM donors WHERE id = ?", (donor_id,)).fetchone()
        return dict(row) if row else None

    def donor_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM donors").fetchone()[0])

    def donors(self, *, min_priority: int | None = None, country: str | None = None,
               circle: int | None = None, status: str | None = None,
               goods: str | None = None, search: str | None = None,
               order: str = "priority", limit: int = 500) -> list[dict[str, Any]]:
        sql = "SELECT * FROM donors WHERE 1=1"
        args: list[Any] = []
        if min_priority is not None:
            sql += " AND priority >= ?"
            args.append(min_priority)
        if country:
            sql += " AND country = ?"
            args.append(country)
        if circle:
            sql += " AND circle = ?"
            args.append(circle)
        if status:
            sql += " AND status = ?"
            args.append(status)
        if goods:
            sql += " AND goods = ?"
            args.append(goods)
        if search:
            sql += " AND (name LIKE ? OR what LIKE ? OR recipient LIKE ?)"
            args += [f"%{search}%"] * 3
        order_sql = {"priority": "priority DESC, event_date DESC",
                     "date": "event_date DESC",
                     "country": "country, priority DESC"}.get(order, "priority DESC")
        sql += f" ORDER BY {order_sql} LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(sql, args)]

    def set_donor(self, donor_id: int, **fields: Any) -> None:
        allowed = {"name", "country", "site", "contact_person", "contact_email",
                   "contact_phone", "lang", "status", "letter_sent_at",
                   "followup_at", "notes", "priority", "circle", "goods"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        sets["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cols = ", ".join(f"{k} = ?" for k in sets)
        self.conn.execute(f"UPDATE donors SET {cols} WHERE id = ?",
                          (*sets.values(), donor_id))
        self.conn.commit()

    def prune_donors(self, live_uids: set[str]) -> int:
        """Видаляє автоматичні картки (status='new', без правок), чиї новини
        більше не належать стрічці 🤝 — щоб у реєстрі не накопичувався шум."""
        rows = self.conn.execute(
            "SELECT id, uid FROM donors WHERE status = 'new' AND contact_email = '' "
            "AND notes = '' AND site = ''").fetchall()
        drop = [r["id"] for r in rows if r["uid"] not in live_uids]
        for did in drop:
            self.conn.execute("DELETE FROM donors WHERE id = ?", (did,))
        self.conn.commit()
        return len(drop)

    def donor_stats(self) -> dict[str, Any]:
        c = self.conn.execute
        by_status = {r[0]: r[1] for r in c("SELECT status, COUNT(*) FROM donors GROUP BY status")}
        by_circle = {r[0]: r[1] for r in c("SELECT circle, COUNT(*) FROM donors GROUP BY circle")}
        by_country = {r[0]: r[1] for r in c(
            "SELECT country, COUNT(*) FROM donors GROUP BY country ORDER BY COUNT(*) DESC")}
        return {
            "total": self.donor_count(),
            "hot": int(c("SELECT COUNT(*) FROM donors WHERE priority >= 7").fetchone()[0]),
            "warm": int(c("SELECT COUNT(*) FROM donors WHERE priority BETWEEN 4 AND 6").fetchone()[0]),
            "cold": int(c("SELECT COUNT(*) FROM donors WHERE priority < 4").fetchone()[0]),
            "by_status": by_status, "by_circle": by_circle, "by_country": by_country,
        }

    def stats(self) -> dict[str, Any]:
        c = self.conn.execute
        total = c("SELECT COUNT(*) FROM opportunities").fetchone()[0]
        high = c("SELECT COUNT(*) FROM opportunities WHERE band='high'").fetchone()[0]
        med = c("SELECT COUNT(*) FROM opportunities WHERE band='medium'").fetchone()[0]
        soon = c(
            "SELECT COUNT(*) FROM opportunities WHERE deadline_at IS NOT NULL "
            "AND deadline_at >= ? AND deadline_at <= datetime('now','+30 days')",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
        ).fetchone()[0]
        last = c("SELECT finished_at, collected, new_items FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        by_source = [dict(r) for r in c(
            "SELECT source_name, COUNT(*) n, MAX(score) best FROM opportunities "
            "GROUP BY source_name ORDER BY n DESC"
        )]
        tracks = {r[0]: r[1] for r in c(
            "SELECT track, COUNT(*) FROM opportunities GROUP BY track")}
        equip = c("SELECT COUNT(*) FROM opportunities WHERE equipment = 1").fetchone()[0]
        resolved = c("SELECT COUNT(*) FROM opportunities "
                     "WHERE apply_url IS NOT NULL AND apply_url <> ''").fetchone()[0]
        hidden = {r[0] or "?": r[1] for r in c(
            "SELECT hide_reason, COUNT(*) FROM opportunities "
            "WHERE COALESCE(actionable,1)=0 GROUP BY hide_reason")}
        budgets = {r[0] or "unknown": r[1] for r in c(
            "SELECT COALESCE(budget_band,'unknown'), COUNT(*) FROM opportunities "
            "GROUP BY COALESCE(budget_band,'unknown')")}
        regions = {r[0] or "?": r[1] for r in c(
            "SELECT region, COUNT(*) FROM opportunities GROUP BY region")}
        benef = {r[0]: r[1] for r in c(
            "SELECT beneficiary, COUNT(*) FROM opportunities GROUP BY beneficiary")}
        return {
            "total": total, "high": high, "medium": med, "deadline_30d": soon,
            "tracks": tracks, "equipment": equip,
            "regions": regions, "ua": regions.get("UA", 0), "resolved": resolved,
            "hidden": sum(hidden.values()), "hidden_by_reason": hidden,
            "feed_ua": c("SELECT COUNT(*) FROM opportunities WHERE COALESCE(actionable,1)=1 "
                         "AND COALESCE(feed,'ua')='ua'").fetchone()[0],
            "feed_eu": c("SELECT COUNT(*) FROM opportunities WHERE COALESCE(actionable,1)=1 "
                         "AND COALESCE(feed,'ua')='eu'").fetchone()[0],
            "feed_aid": c("SELECT COUNT(*) FROM opportunities WHERE COALESCE(actionable,1)=1 "
                          "AND COALESCE(feed,'ua')='aid'").fetchone()[0],
            "feed_edu": c("SELECT COUNT(*) FROM opportunities WHERE COALESCE(actionable,1)=1 "
                          "AND COALESCE(feed,'ua')='edu'").fetchone()[0],
            "actionable": c("SELECT COUNT(*) FROM opportunities "
                            "WHERE COALESCE(actionable,1)=1").fetchone()[0],
            "budgets": budgets,
            "budget_known": sum(v for k, v in budgets.items() if k != "unknown"),
            "waste": tracks.get("waste", 0), "education": tracks.get("education", 0),
            "communal": benef.get("communal", 0) + benef.get("both", 0),
            "private": benef.get("private", 0) + benef.get("both", 0),
            "last_run": dict(last) if last else None, "by_source": by_source,
        }

    def budget_bands_in_db(self) -> list[str]:
        return [r[0] or "unknown" for r in self.conn.execute(
            "SELECT DISTINCT COALESCE(budget_band,'unknown') FROM opportunities")]

    def tracks_in_db(self) -> list[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT track, COUNT(*) n FROM opportunities GROUP BY track ORDER BY n DESC") if r[0]]

    def sources_in_db(self) -> list[tuple[str, str]]:
        return [(r["source_id"], r["source_name"]) for r in self.conn.execute(
            "SELECT DISTINCT source_id, source_name FROM opportunities ORDER BY source_name")]


def _days_left(deadline: str | None) -> int | None:
    if not deadline:
        return None
    try:
        from .screening import norm_date
        norm = norm_date(deadline)
        if not norm:
            return None
        dt = datetime.fromisoformat(norm)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - datetime.now(timezone.utc)).days
