"""ARPEJ availability watch: dynamic discovery, no fixed residence allowlist."""
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.arpej.fr"
CATALOG = f"{BASE}/fr/nos-residences/?related_city=52524&iam=jeunes-actifs&show_if_full=true"
STATE = Path("state_idf_jeunes_actifs.json")
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
DELAY = float(os.environ.get("REQUEST_DELAY_SECONDS", "0.7"))
IDF_POSTCODES = ("75", "77", "78", "91", "92", "93", "94", "95")
COUNT = re.compile(r"\b(\d+)\s+logements?\s+disponibles?\b", re.I)
ZERO = re.compile(r"\bcomplet(?:e|s|es)?\b", re.I)
PROFILE = re.compile(r"Logements\s+cl[eé]s\s+en\s+main\s+pour\s*:\s*(.{0,110})", re.I)
POSTCODE = re.compile(r"\b(\d{5})\b")
LIMITED = re.compile(r"\bacc[eè]s\s+limit[eé]\b", re.I)
RESERVED = re.compile(r"(?:r[eé]sidence|logements?|attribution)\s+(?:(?:exclusivement|uniquement)\s+)?r[eé]serv[eé]e?s?\s+(?:aux?|[aà]|pour)\s+.{3,110}", re.I)
LOG = logging.getLogger("arpej")


def fetch(session, url):
    response = session.get(url, timeout=25)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def candidates(soup):
    """Discover residence links from the catalog, regardless of current profile filters."""
    result = {}
    for a in soup.select('a[href]'):
        url = urljoin(BASE, a['href']).split('#', 1)[0].split('?', 1)[0]
        parsed = urlparse(url)
        if parsed.netloc not in ("arpej.fr", "www.arpej.fr") or not parsed.path.startswith('/fr/residence/'):
            continue
        key = parsed.path.rstrip('/')
        if key not in result:
            result[key] = {"url": url, "catalog_name": a.get_text(' ', strip=True)}
    if len(result) < 10:
        raise RuntimeError(f"Catalogue incomplet : seulement {len(result)} liens de residences")
    return result


def parse_residence(soup, url, catalog_name):
    """Eligibility and geography are re-evaluated on every scan from the residence page."""
    main = soup.select_one('main') or soup.body or soup
    # Remove related residences, testimonials and footer: these may mention other profiles / access restrictions.
    heading = main.find('h1')
    if heading is None:
        raise ValueError("Titre h1 absent")
    name = heading.get_text(' ', strip=True) or catalog_name
    # The page's essential fields should appear in the header, before detailed content.
    texts = list(main.stripped_strings)
    heading_text = heading.get_text(' ', strip=True)
    index = next((i for i, t in enumerate(texts) if t == heading_text), None)
    if index is None:
        raise ValueError("En-tete de fiche introuvable")
    header = ' '.join(texts[index:index + 42])[:2500]
    p = PROFILE.search(header)
    if not p:
        raise ValueError("Champ d'eligibilite absent")
    # Stop capture at the address; prevents reading a later unrelated text containing young actives.
    profile_value = re.split(r'\b\d{5}\b|Voir sur la carte|\b\d+\s*,\s*(?:rue|avenue|boulevard)\b', p.group(1), maxsplit=1, flags=re.I)[0]
    profile_value = profile_value[:100]
    eligible = bool(re.search(r'\bjeunes?\s+actifs?\b', profile_value, re.I))
    postcode = POSTCODE.search(header)
    # No postcode? Don't guess geographical eligibility from city names.
    if not postcode:
        raise ValueError("Code postal non trouve dans l'en-tete")
    if not postcode.group(1).startswith(IDF_POSTCODES) or not eligible:
        return None
    # For young-active pages in IDF, the full 5-digit zip is sufficient.
    # The postcode matcher itself only accepts the eight IDF departments.
    # Availability is explicitly labelled 'Disponibilite' in the fiche.
    av_context = re.search(r'Disponibilit[eé]\s+(.{0,90})', header, re.I)
    if not av_context:
        raise ValueError("Champ Disponibilite absent")
    availability_text = av_context.group(1)
    match = COUNT.search(availability_text)
    if match:
        available = int(match.group(1))
    elif ZERO.search(availability_text):
        available = 0
    else:
        raise ValueError("Disponibilite illisible")
    # Only the residence's own introductory section, never related residences.
    head_until_detail = re.split(r'Votre r[eé]sidence|Votre logement|Autres r[eé]sidences', header, maxsplit=1, flags=re.I)[0]
    limited = bool(LIMITED.search(head_until_detail) or LIMITED.search(" ".join(texts[max(0, index-4):index])))
    reservation = RESERVED.search(head_until_detail)
    access = ('Accès limité' if limited else reservation.group(0).strip() if reservation else None)
    return {"name": name, "url": url, "available": available,
            "postcode": postcode.group(1), "access": access}


def scan(session):
    catalog = candidates(fetch(session, CATALOG))
    found = {}
    failures = []
    for i, (key, meta) in enumerate(catalog.items(), start=1):
        try:
            item = parse_residence(fetch(session, meta['url']), meta['url'], meta['catalog_name'])
            if item is not None:
                found[key] = item
        except (requests.RequestException, ValueError) as exc:
            failures.append((key, str(exc)))
            LOG.warning("Fiche non valide %s: %s", meta['url'], exc)
        if i < len(catalog):
            time.sleep(DELAY)
    LOG.info("%d fiches consultees, %d IDF jeunes actifs, %d echec(s)", len(catalog), len(found), len(failures))
    if not found:
        raise RuntimeError("Aucune residence eligible detectee, scan abandonne")
    if len(failures) > max(5, len(catalog) // 5):
        raise RuntimeError("Trop de fiches en erreur, historique conserve")
    return found, failures


def notify(session, item, before):
    if not WEBHOOK:
        raise RuntimeError("Secret DISCORD_WEBHOOK_URL absent")
    access = f"\n🔒 {item['access']}" if item.get('access') else ""
    content = (f"🏠 **ARPEJ — Nouvelle disponibilité (IDF · Jeunes actifs)**\n"
               f"**{item['name']}** ({item['postcode']})\n"
               f"{before} → **{item['available']} logement(s) disponible(s)**"
               f"{access}\n{item['url']}")
    r = session.post(WEBHOOK, json={"content": content[:1900], "allowed_mentions": {"parse": []}}, timeout=20)
    r.raise_for_status()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    session = requests.Session()
    session.headers.update({"User-Agent": "ARPEJ-personal-availability-monitor/3.0 (noncommercial; courteous polling)", "Accept-Language": "fr-FR,fr;q=0.9"})
    current, failed = scan(session)
    previous = json.loads(STATE.read_text()) if STATE.exists() else {}
    first_run = not STATE.exists()
    # Never convert failed pages to zero, and preserve already seen IDs for reappearances.
    changes = [(key, value, previous.get(key, {}).get('available', 0))
               for key, value in current.items()
               if not first_run and value['available'] > previous.get(key, {}).get('available', 0)]
    for _, item, before in changes:
        notify(session, item, before)
    previous.update(current)
    STATE.write_text(json.dumps(previous, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    LOG.info("%d residences eligibles, %d disponibles, %d alertes, %d fiches en erreur%s",
             len(current), sum(v['available'] > 0 for v in current.values()), len(changes), len(failed),
             ' (premier scan sans notification)' if first_run else '')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        LOG.exception("Scan ARPEJ interrompu, historique non remplace")
        raise SystemExit(1)
