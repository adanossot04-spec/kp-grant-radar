"""Пошук першоджерела гранту — сторінки, де його насправді подають.

Навіщо: каталоги («Час Змін», GetGrant, ГУРТ) і новини — це посередники.
Подавати заявку треба на сайті донора (ПРООН, ЄС, Дія.Бізнес, фонд тощо).
Цей модуль відкриває сторінку оголошення, знаходить у ній посилання на
першоджерело / форму подачі й зберігає його в полях `apply_url`, `apply_host`.

Для новин із Google News (посилання веде на SPA-сторінку Google) спершу
відновлюємо пряме посилання на статтю через новинний пошук Bing.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "uk,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml",
}

# Сайти-посередники: їхні власні сторінки не вважаємо першоджерелом
AGGREGATORS = (
    "chaszmin.com.ua", "gurt.org.ua", "getgrant.ua", "prostir.ua", "hromady.org",
    "decentralization.ua", "news.google.com", "bing.com", "ednannia.ua",
    "biggggidea.com", "grantodavets", "zagoriy.foundation",
    "grant.market", "grantradar.com.ua", "gidinvest.com", "granty.com.ua",
    "grants.in.ua", "gurt.org", "dyvys.info", "sprotyvua",
)

# Сервіси подачі заявок — найсильніший сигнал
FORM_HOSTS = ("forms.gle", "docs.google.com", "forms.office.com", "typeform.com",
              "airtable.com", "surveymonkey", "jotform", "formstack", "smartsheet",
              "submit.", "apply.", "grants.", "kobotoolbox")

# Домени донорів і офіційних програм
DONOR_HINTS = ("undp.org", "unicef.org", "un.org", "iom.int", "who.int", "unesco.org",
               "europa.eu", "ec.europa.eu", "eacea", "eeas.europa.eu", "euneighbours",
               "usaid.gov", "state.gov", "giz.de", "sida.se", "norad.no", "britishcouncil",
               "worldbank.org", "ebrd.com", "eib.org", "nefco.int", "coebank.org",
               "diia.gov.ua", "gov.ua", "erasmusplus.org.ua", "ucf.in.ua",
               "peopleinneed.net", "nras.org.ua", "irf.ua", "visegradfund.org",
               "zagoriy", "caritas", "dai.com", "chemonics", "mercycorps", "nrc.no",
               "rescue.org", "helvetas", "undp", "ukrainefacility", "e5p.eu")

JUNK_HOSTS = ("google.com/search", "google.", "bing.com", "yandex.", "wikipedia.org",
              "creativecommons.org", "w3.org", "mozilla.org", "wordpress.org",
              "adobe.com", "gnu.org", "unsplash.com", "cloudflare.com",
              "archive.org", "translate.", "webcache.", "amp.", "apple.com", "play.google")

SOCIAL = ("facebook.", "instagram.", "twitter.", "x.com/", "t.me/", "telegram.",
          "youtube.", "youtu.be", "linkedin.", "tiktok.", "pinterest.", "wa.me",
          "whatsapp", "viber", "mailto:", "tel:", "sharer.php", "share?", "/share",
          "addtoany", "threads.net")

ASSET = re.compile(r"\.(png|jpe?g|gif|svg|webp|ico|css|js|woff2?|mp4|zip)(\?|$)", re.I)

APPLY_WORDS = re.compile(
    r"(подати|подач|заявк|аплікац|рееєстрац|реєстрац|анкет|форм[аиу]\b|деталі|детальн|"
    r"дізнатися більше|за посиланням|джерело|першоджерел|офіційн|сайт програми|тут\b|"
    r"умови участі|оголошенн|apply|application|submit|registration|call page|"
    r"more (?:info|details)|official|source|website|guidelines)", re.I)

CONTENT_SELECTORS = (".entry-content", ".post-content", "[itemprop='articleBody']",
                     "article .content", "article", "main", ".news-detail", ".content")


def _host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "").lower()
    except ValueError:
        return ""


def is_aggregator(url: str) -> bool:
    h = _host(url)
    return any(a in h for a in AGGREGATORS)


def _score_link(text: str, href: str, page_host: str) -> int:
    h = _host(href)
    if not h or ASSET.search(href):
        return -99
    if any(s in href.lower() for s in SOCIAL):
        return -99
    if h == page_host or h.endswith("." + page_host) or page_host.endswith("." + h):
        return -99
    if any(a in h for a in AGGREGATORS):
        return -50
    if any(j in h for j in JUNK_HOSTS) and not h.startswith("docs.google"):
        return -99

    score = 1
    if any(f in h for f in FORM_HOSTS):
        score += 6
    if any(d in h for d in DONOR_HINTS):
        score += 4
    if h.endswith((".gov.ua", ".europa.eu", ".int", ".org", ".org.ua")):
        score += 1
    if APPLY_WORDS.search(text or ""):
        score += 3
    if len(text or "") > 120:                      # підозріло довгий «текст-посилання»
        score -= 1
    if re.search(r"(privacy|cookie|terms|політик|умови використан)", (text or "") + href, re.I):
        score -= 5
    return score


def extract_primary(html: str, page_url: str) -> tuple[str, str]:
    """Повертає (посилання на першоджерело, видимий текст посилання)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("header, footer, nav, aside, .menu, .sidebar, .related, .widget"):
        tag.decompose()

    body = None
    for sel in CONTENT_SELECTORS:
        body = soup.select_one(sel)
        if body and len(body.get_text(strip=True)) > 200:
            break
    body = body or soup
    page_host = _host(page_url)

    best: tuple[int, str, str] = (0, "", "")
    for a in body.find_all("a", href=True):
        href = urllib.parse.urljoin(page_url, a["href"].strip())
        if not href.startswith("http"):
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        sc = _score_link(text, href, page_host)
        if sc > best[0]:
            best = (sc, href, text[:120])
    return (best[1], best[2]) if best[0] >= 2 else ("", "")


def _gnews_decode(url: str, timeout: int = 25) -> str:
    """Розкодовує посилання news.google.com у справжню адресу статті.

    Google News віддає токен `CBMi...`, а не URL. Офіційний спосіб дістати
    оригінал — внутрішній виклик `batchexecute`: зі сторінки статті беремо
    підпис (`data-n-a-sg`), мітку часу й id, і запитуємо ними адресу.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        div = BeautifulSoup(r.text, "html.parser").select_one("c-wiz > div")
        if not div:
            return ""
        sig, ts, aid = div.get("data-n-a-sg"), div.get("data-n-a-ts"), div.get("data-n-a-id")
        if not (sig and ts and aid):
            return ""
        payload = ["Fbv4je",
                   f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,'
                   f'null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
                   f'"{aid}",{ts},"{sig}"]']
        rr = requests.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                           headers={**HEADERS,
                                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                           data={"f.req": json.dumps([[payload]])}, timeout=timeout)
        rr.raise_for_status()
        part = json.loads(rr.text.split("\n\n")[1])[:2]
        out = json.loads(part[0][2])[1]
        return out if isinstance(out, str) and out.startswith("http") else ""
    except Exception as exc:
        log.debug("gnews decode %s: %s", url[-25:], exc)
        return ""


def _bing_direct_link(title: str) -> str:
    """Відновлює пряме посилання на статтю за заголовком (Bing News RSS)."""
    try:
        r = requests.get("https://www.bing.com/news/search",
                         params={"q": title[:120], "format": "RSS", "setmkt": "uk-UA"},
                         headers=HEADERS, timeout=25)
        text = r.text.replace("&amp;", "&")
        for raw in re.findall(r"<link>(.*?)</link>", text):
            m = re.search(r"[?&]url=([^&<]+)", raw)
            if m:
                return urllib.parse.unquote(m.group(1))
            if "bing.com" not in raw and raw.startswith("http"):
                return raw
    except Exception as exc:
        log.debug("bing lookup '%s': %s", title[:40], exc)
    return ""


SHORTENERS = ("bit.ly", "cutt.ly", "tinyurl.com", "is.gd", "surl.li",
              "goo.gl", "t.co", "ow.ly", "shorturl.at", "rb.gy")


def _unshorten(url: str, timeout: int = 15) -> str:
    """Розгортає короткі посилання (bit.ly тощо) у кінцевий URL."""
    if not url or not any(s in _host(url) for s in SHORTENERS):
        return url
    try:
        r = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.url and _host(r.url) and not any(s in _host(r.url) for s in SHORTENERS):
            return r.url
    except Exception:
        pass
    return url


_DONORS_CACHE: list[dict[str, Any]] = []


def _load_donors() -> list[dict[str, Any]]:
    """Читає config/donors.yaml (назва донора → сторінка його конкурсів)."""
    global _DONORS_CACHE
    if _DONORS_CACHE:
        return _DONORS_CACHE
    try:
        import yaml
        root = Path(__file__).resolve().parents[2]
        data = yaml.safe_load((root / "config" / "donors.yaml").read_text(encoding="utf-8"))
        _DONORS_CACHE = [d for d in (data or {}).get("donors", []) if d.get("url")]
    except Exception as exc:
        log.debug("donors.yaml: %s", exc)
        _DONORS_CACHE = []
    return _DONORS_CACHE


def _donor_page(title: str | None, summary: str | None, body: str = "") -> tuple[str, str]:
    """Останній фолбек: визначає донора за згадкою в тексті анонсу.

    Повертає (сторінка конкурсів донора, мітка). Це не форма конкретної
    заявки, тому мітка окрема — «сторінка донора: …», і в інтерфейсі кнопка
    підписується інакше, щоб не вводити в оману.

    Щоб не ловити випадкові згадки, у заголовку й описі приймаємо будь-який
    збіг, а в тілі статті — лише довгі однозначні назви (від 6 символів).
    """
    strong = " ".join(x for x in (title, summary) if x).lower()
    weak = (body or "").lower()
    if len(strong) + len(weak) < 20:
        return "", ""
    best: tuple[int, str, str] = (0, "", "")
    for d in _load_donors():
        for pat in d.get("match", []):
            pat = str(pat).lower().strip()
            if len(pat) < 3:
                continue
            hit = pat in strong or (len(pat) >= 6 and pat in weak)
            if hit and len(pat) > best[0]:
                best = (len(pat), d["url"], f"сторінка донора: {d.get('name', _host(d['url']))}")
    return best[1], best[2]


_SEARCH_LOCK = threading.Lock()
_LAST_SEARCH = [0.0]
SEARCH_MIN_INTERVAL = 1.3          # с, щоб пошуковик не блокував IP


def _ddg_lite(query: str, timeout: int = 25) -> list[tuple[str, str]]:
    """Безкоштовний веб-пошук (DuckDuckGo Lite, POST). → [(текст, url)]."""
    with _SEARCH_LOCK:                      # запити строго по черзі
        pause = SEARCH_MIN_INTERVAL - (time.time() - _LAST_SEARCH[0])
        if pause > 0:
            time.sleep(pause)
        try:
            r = requests.post("https://lite.duckduckgo.com/lite/",
                              data={"q": query[:180]}, headers=HEADERS, timeout=timeout)
            _LAST_SEARCH[0] = time.time()
            r.raise_for_status()
            html = r.text
        except Exception as exc:
            _LAST_SEARCH[0] = time.time()
            log.debug("ddg '%s': %s", query[:40], exc)
            return []

    out: list[tuple[str, str]] = []
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http") or "duckduckgo.com" in href:
            continue
        out.append((" ".join(a.get_text(" ", strip=True).split())[:120], href))
    return out


def _page_published(html: str) -> str:
    """Дата публікації сторінки — потрібна, щоб правильно трактувати
    дати без року («заявки приймаються з 20 червня по 20 липня»)."""
    for pat in (r'"datePublished"\s*:\s*"([^"]+)"',
                r'property=["\']article:published_time["\']\s+content=["\']([^"\']+)',
                r'<time[^>]+datetime=["\']([^"\']+)'):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1)
    return ""


def _body_text(html: str) -> str:
    """Текст статті без меню й футера — щоб донора не «вгадати» по шапці сайту."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("header, footer, nav, aside, .menu, .sidebar, .related, .widget"):
        tag.decompose()
    for sel in CONTENT_SELECTORS:
        body = soup.select_one(sel)
        if body and len(body.get_text(strip=True)) > 200:
            return body.get_text(" ", strip=True)
    return soup.get_text(" ", strip=True)


def _bing_news_candidates(title: str, limit: int = 4) -> list[str]:
    """Прямі посилання на статті про цю ж програму (новинний індекс Bing)."""
    out: list[str] = []
    try:
        r = requests.get("https://www.bing.com/news/search",
                         params={"q": title[:120], "format": "RSS", "setmkt": "uk-UA"},
                         headers=HEADERS, timeout=25)
        text = r.text.replace("&amp;", "&")
        for raw in re.findall(r"<link>(.*?)</link>", text):
            m = re.search(r"[?&]url=([^&<]+)", raw)
            u = urllib.parse.unquote(m.group(1)) if m else raw
            if u.startswith("http") and "bing.com" not in u and u not in out:
                out.append(u)
    except Exception as exc:
        log.debug("bing news '%s': %s", title[:40], exc)
    return out[:limit]


def _from_other_articles(title: str, origin_host: str, timeout: int = 20) -> tuple[str, str]:
    """Шукає посилання на донора в чужих публікаціях про ту саму програму."""
    for u in _bing_news_candidates(title):
        h = _host(u)
        if not h or h == origin_host or any(a in h for a in AGGREGATORS):
            continue
        try:
            r = requests.get(u, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            if not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding or "utf-8"
            link, label = extract_primary(r.text, u)
        except Exception:
            continue
        link = _unshorten(link)
        if link and any(d in _host(link) for d in DONOR_HINTS + FORM_HOSTS):
            return link, (label or "знайдено в публікації " + h)[:120]
    return "", ""


def _search_official(title: str, origin_host: str) -> tuple[str, str]:
    """Коли в тексті анонсу посилання немає — шукаємо сайт донора пошуковиком.

    Беремо лише впевнені влучання: сервіс подачі заявок або домен донора
    (ПРООН, ЄС, Дія, gov.ua тощо). Каталоги й новини свідомо відкидаємо,
    інакше замість першоджерела отримаємо ще одного посередника.
    """
    title = (title or "").strip()
    if len(title) < 15:
        return "", ""
    best: tuple[int, str, str] = (0, "", "")
    for query in (f"{title} подати заявку", f"{title} офіційний сайт"):
        for text, href in _ddg_lite(query):
            h = _host(href)
            if not h or h == origin_host or ASSET.search(href):
                continue
            if any(a in h for a in AGGREGATORS) or any(s in href.lower() for s in SOCIAL):
                continue
            if any(j in h for j in JUNK_HOSTS) and not h.startswith("docs.google"):
                continue
            sc = 0
            if any(f in h for f in FORM_HOSTS):
                sc += 6
            if any(d in h for d in DONOR_HINTS):
                sc += 4
            if h.endswith(".gov.ua"):
                sc += 2
            if sc and APPLY_WORDS.search(text):
                sc += 1
            if sc > best[0]:
                best = (sc, href, text)
        if best[0] >= 6:                    # форма подачі — далі не шукаємо
            break
    if best[0] >= 4:
        return best[1], (best[2] or "знайдено пошуком")[:120]
    return "", ""


def resolve_one(item: dict[str, Any], timeout: int = 25) -> dict[str, str]:
    """Знаходить першоджерело для одного запису."""
    url = item.get("url") or ""
    page_url = url

    # Google News віддає SPA — відновлюємо пряме посилання на статтю
    if "news.google.com" in url:
        # 1) офіційне розкодування токена Google News, 2) запасний пошук у Bing
        page_url = _gnews_decode(url) or _bing_direct_link(item.get("title") or "") or ""
        if not page_url:
            return {}

    try:
        r = requests.get(page_url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding or "utf-8"
        html = r.text
    except Exception as exc:
        log.debug("resolve %s: %s", page_url[:60], exc)
        # навіть якщо сторінка не відкрилась — пряме посилання вже корисне
        out = {"article_url": page_url} if page_url != url else {}
        a_url, a_label = ("", "")
        if item.get("allow_search"):
            a_url, a_label = _search_official(item.get("title") or "", _host(page_url))
            if not a_url:
                a_url, a_label = _from_other_articles(item.get("title") or "", _host(page_url))
        if not a_url:
            a_url, a_label = _donor_page(item.get("title"), item.get("summary"))
        if a_url:
            out.update(apply_url=a_url, apply_host=_host(a_url), apply_label=a_label)
        return out

    apply_url, label = extract_primary(html, page_url)
    apply_url = _unshorten(apply_url)
    body = _body_text(html)
    if not apply_url and item.get("allow_search"):
        # 1) звичайний веб-пошук (працює, доки пошуковик не блокує IP)
        apply_url, label = _search_official(item.get("title") or "", _host(page_url))
        # 2) чужі публікації про цю ж програму — там посилання часто є
        if not apply_url:
            apply_url, label = _from_other_articles(item.get("title") or "", _host(page_url))
    # 3) останній шанс — офіційна сторінка донора за згадкою в тексті
    if not apply_url and item.get("allow_donor", True):
        apply_url, label = _donor_page(item.get("title"), item.get("summary"),
                                       body[:3000])
    out: dict[str, str] = {}
    from .screening import extract_deadline          # дедлайн зі сторінки оголошення
    deadline = extract_deadline(
        item.get("title") or "", body,
        published=_page_published(html) or item.get("published_at"))
    if deadline:
        out["deadline_at"] = deadline
    if page_url != url:
        out["article_url"] = page_url
    if apply_url:
        out["apply_url"] = apply_url
        out["apply_host"] = _host(apply_url)
        out["apply_label"] = label
    return out


def resolve(db, min_score: int = 35, limit: int = 120, workers: int = 8,
            only_unresolved: bool = True, search_min: int = 35) -> int:
    """Масово визначає першоджерела для записів із каталогів і новин."""
    sql = ("SELECT uid, title, url, summary, source_id, published_at, score "
           "FROM opportunities "
           "WHERE score >= ? AND (deadline_at IS NULL OR deadline_at = '' "
           "      OR deadline_at >= ?) ")
    args: list[Any] = [min_score, datetime.now(timezone.utc).isoformat(timespec="seconds")]
    if only_unresolved:
        sql += "AND (resolved_at IS NULL OR resolved_at = '') "
    sql += "ORDER BY score DESC LIMIT ?"
    args.append(limit)

    rows = [dict(r) for r in db.conn.execute(sql, args)]
    rows = [r for r in rows if is_aggregator(r["url"])]
    for r in rows:                       # пошуковий фолбек — лише для вартісних позицій
        r["allow_search"] = (r.get("score") or 0) >= search_min
    if not rows:
        return 0

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    found = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(resolve_one, rows))
    for row, res in zip(rows, results):
        db.conn.execute(
            "UPDATE opportunities SET apply_url=?, apply_host=?, apply_label=?, "
            "article_url=?, resolved_at=?, deadline_at=COALESCE(?, deadline_at) WHERE uid=?",
            (res.get("apply_url", ""), res.get("apply_host", ""),
             res.get("apply_label", ""), res.get("article_url", ""), ts,
             res.get("deadline_at"), row["uid"]))
        if res.get("apply_url"):
            found += 1
    db.conn.commit()
    log.info("Першоджерела: опрацьовано %d, знайдено %d", len(rows), found)
    return found
