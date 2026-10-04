"""CLI агента.

    python -m grant_radar collect      # зібрати та оцінити можливості
    python -m grant_radar rescore      # перерахувати бали після правок profile.yaml
    python -m grant_radar resolve      # знайти першоджерела (де подавати заявку)
    python -m grant_radar screen       # відсіяти новини, вакансії та протерміноване
    python -m grant_radar check        # самоперевірка: чи не лишилось протермінованого
    python -m grant_radar serve        # веб-дашборд на http://0.0.0.0:8000
    python -m grant_radar export       # статичний сайт у docs/ (GitHub Pages)
    python -m grant_radar digest       # дайджест у Markdown + Telegram
    python -m grant_radar sources      # перелік увімкнених джерел
    python -m grant_radar top -n 10 --benef communal   # топ для комунальних
    python -m grant_radar memory       # перевірити заповненість config/memory.yaml
    python -m grant_radar draft --uid <id>             # чернетка заявки з пам'яті
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import config
from .db import Database
from .scoring import BAND_LABEL


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="grant_radar", description="Грант-радар для КП")
    ap.add_argument("command",
                    choices=["collect", "rescore", "resolve", "screen", "check", "serve", "export", "digest",
                             "sources", "top", "memory", "draft",
                             "donors", "letter", "contacts"])
    ap.add_argument("--no-llm", action="store_true", help="не викликати LLM навіть за наявності ключа")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("-n", "--limit", type=int, default=15)
    ap.add_argument("--min-score", type=int, default=40)
    ap.add_argument("--all", action="store_true",
                    help="для resolve: перевіряти й ті записи, що вже опрацьовані")
    ap.add_argument("--fetch", type=int, default=0,
                    help="для screen: скільки сторінок довантажити заради пошуку дедлайну")
    ap.add_argument("--redate", action="store_true",
                    help="для screen: перерахувати дедлайни з тексту (чистка хибних дат)")
    ap.add_argument("--search-min", type=int, default=35,
                    help="для resolve: з якого бала вмикати пошук донора в інтернеті")
    ap.add_argument("--out", default=None, help="куди писати дайджест/експорт")
    ap.add_argument("--uid", default=None, help="id можливості для команди draft")
    ap.add_argument("--org", default=None, help="id організації з memory.yaml")
    ap.add_argument("--donor", type=int, default=None,
                    help="id донора з реєстру для команди letter")
    ap.add_argument("--lang", default=None,
                    help="мова листа: hu | de | pl | en | uk (типово — мова країни донора)")
    ap.add_argument("--min-priority", type=int, default=4,
                    help="для donors/letter: мінімальний пріоритет донора")
    ap.add_argument("--benef", default=None,
                    choices=["communal", "private", "both", "unknown"],
                    help="фільтр за типом заявника для команди top")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    log = logging.getLogger("grant_radar")

    if args.command == "sources":
        for s in config.load_sources():
            print(f"  [{s.get('region','?'):3}] {s['id']:<18} {s['type']:<6} "
                  f"вага {s.get('weight',1.0)}  {s['name']}")
        return 0

    db = Database(config.DB_PATH)

    if args.command == "collect":
        from .pipeline import run
        log.info("🛰️  Сканування джерел…")
        stats = run(db=db, use_llm=not args.no_llm)
        if stats["errors"]:
            log.info("⚠️  Помилки: %s", "; ".join(stats["errors"][:5]))
        return 0

    if args.command == "rescore":
        from .pipeline import rescore
        rescore(db)
        return 0

    if args.command == "resolve":
        from .resolve import resolve
        found = resolve(db, min_score=args.min_score, limit=max(args.limit, 120),
                        only_unresolved=not args.all, search_min=args.search_min)
        log.info("🔗 Знайдено першоджерел: %d", found)
        return 0

    if args.command == "screen":
        from .screening import REASON_TEXT, screen_all
        res = screen_all(db, fetch=args.fetch, redate=args.redate)
        log.info("✅ У стрічці залишається: %d", res["shown"])
        for key, text in REASON_TEXT.items():
            if res.get(key):
                log.info("   — приховано %4d: %s", res[key], text)
        log.info("🗓 Дедлайнів знайдено в тексті: %d; знято хибних: %d",
                 res["deadlines"], res.get("cleared", 0))
        return 0

    if args.command == "check":
        from .screening import selfcheck
        problems = selfcheck(db)
        if not problems:
            log.info("✅ Самоперевірка пройдена: протермінованих і зламаних дат немає")
            return 0
        log.error("❌ Знайдено проблем: %d", len(problems))
        for line in problems[:30]:
            log.error("   — %s", line)
        return 1

    if args.command == "serve":
        import uvicorn
        log.info("🌐 Дашборд: http://%s:%s", args.host, args.port)
        uvicorn.run("grant_radar.web:app", host=args.host, port=args.port, log_level="info")
        return 0

    if args.command == "donors":
        from . import donors as donors_mod
        res = donors_mod.rebuild(db)
        st = db.donor_stats()
        log.info("🤝 Реєстр донорів: +%d нових, оновлено %d, усього %d",
                 res["added"], res["updated"], res["total"])
        log.info("   🔥 гарячих (7+): %d · 🟡 теплих (4–6): %d · ⚪ холодних: %d",
                 st["hot"], st["warm"], st["cold"])
        log.info("   кола: %s", ", ".join(
            f"{donors_mod.CIRCLE_LABEL.get(k, k)} — {v}" for k, v in sorted(st["by_circle"].items())))
        csv_path = donors_mod.export_csv(db)
        log.info("   📊 CSV-реєстр: %s", csv_path)
        log.info("")
        log.info("   %-4s %-3s %-26s %-22s %s", "бал", "кр", "донор", "що передавав", "статус")
        for d in db.donors(limit=args.limit, min_priority=None):
            log.info("   %-4s %-3s %-26s %-22s %s", d["priority"], d["country"],
                     (d["name"] or "—")[:26],
                     donors_mod.GOODS_LABEL.get(d["goods"], d["goods"])[:22],
                     donors_mod.STATUS_LABEL.get(d["status"], d["status"]))
        return 0

    if args.command == "letter":
        from . import donors as donors_mod
        if args.donor:
            d = db.donor(args.donor)
            if not d:
                log.error("❌ Донора з id=%s немає в реєстрі", args.donor)
                return 1
            text = donors_mod.build_letter(d, lang=args.lang)
            if args.out:
                Path(args.out).write_text(text, encoding="utf-8")
                log.info("✉️  Лист збережено: %s", args.out)
            else:
                print(text)
            return 0
        paths = donors_mod.write_letters(db, min_priority=args.min_priority,
                                         limit=args.limit if args.limit > 15 else 50)
        log.info("✉️  Підготовлено листів: %d (тека %s)",
                 len(paths), paths[0].parent if paths else "—")
        for p in paths[:10]:
            log.info("   — %s", p.name)
        return 0

    if args.command == "contacts":
        from . import donors as donors_mod
        done = 0
        for d in db.donors(min_priority=args.min_priority, limit=args.limit):
            if not d.get("site") or d.get("contact_email"):
                continue
            emails = donors_mod.find_contacts(d["site"])
            if emails:
                db.set_donor(d["id"], contact_email=", ".join(emails))
                log.info("   ✉️  %s → %s", d["name"], ", ".join(emails))
                done += 1
        log.info("🔎 Знайдено контактів: %d (заповніть поле site у реєстрі, щоб знайти більше)", done)
        return 0

    if args.command == "export":
        from .export import export
        path = export(db, Path(args.out) if args.out else None)
        log.info("📄 Статичний сайт: %s", path)
        return 0

    if args.command == "digest":
        from .digest import build_markdown, send_telegram
        text, uids = build_markdown(db, min_score=args.min_score)
        out = Path(args.out or config.DATA_DIR / "digest.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        log.info("📬 Дайджест: %s (%d позицій)", out, len(uids))
        if send_telegram(text):
            log.info("✅ Надіслано в Telegram")
        if uids:
            db.mark_notified(uids)
        return 0

    if args.command == "memory":
        from . import memory
        orgs = memory.load()
        if not orgs:
            print("config/memory.yaml порожній або відсутній")
            return 1
        for org in orgs:
            comp = memory.completeness(org)
            flag = "активна" if org.get("active", True) else "вимкнена"
            print(f"\n▌ {org.get('id')} ({org.get('entity_type')}, {flag}) — "
                  f"заповнено {comp['percent']}% ({comp['filled']}/{comp['total']} полів)")
            for name, s in comp["sections"].items():
                bar = "█" * (s["percent"] // 10) + "·" * (10 - s["percent"] // 10)
                print(f"    {name:<20} {bar} {s['percent']:>3}%")
            if comp["critical_missing"]:
                print("    ⚠️  критичні незаповнені поля:")
                for path in comp["critical_missing"]:
                    print(f"        - {path}")
        return 0

    if args.command == "draft":
        from .draft import build
        uid = args.uid
        if not uid:
            rows = db.query(min_score=0, limit=1, order="score",
                            beneficiary=args.benef)
            if not rows:
                print("База порожня — спочатку: python -m grant_radar collect")
                return 1
            uid = rows[0]["uid"]
            print(f"Беру найрелевантнішу можливість: {rows[0]['title'][:70]}")
        path = build(uid, db=db, org_id=args.org, use_llm=not args.no_llm)
        print(f"📝 Чернетку заявки збережено: {path}")
        return 0

    if args.command == "top":
        rows = db.query(min_score=0, limit=args.limit, order="score",
                        beneficiary=args.benef)
        from .classify import LABEL as BENEF_LABEL
        for r in rows:
            dl = f" | дедлайн {r['deadline_at'][:10]} ({r['days_left']} дн.)" if r["days_left"] is not None else ""
            print(f"\n{BAND_LABEL.get(r['band'],'')} {r['score']:>3}/100  "
                  f"{BENEF_LABEL.get(r.get('beneficiary','unknown'),'')}  {r['title'][:80]}")
            print(f"     {r['source_name']}{dl}")
            print(f"     {r['url'][:110]}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
