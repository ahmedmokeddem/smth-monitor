import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

URL = "https://www.arpej.fr/fr/nos-residences/?related_city=52524&iam=jeunes-actifs&show_if_full=true"
STATE = Path("state_idf_jeunes_actifs.json")
IDF = set(json.loads(Path("idf_residences.json").read_text()))
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
AVAIL = re.compile(r"\b(\d+)\s+disponible(?:s)?\b", re.I)
COMPLETE = re.compile(r"\bcomplet(?:e|s|es)?\b", re.I)

# Conditions d'accès spéciales indiquées en tête des fiches de résidences.
RESTRICTION = re.compile(
    r"(?:résidence|logements?|attributions?)\s+(?:(?:exclusivement|uniquement)\s+)?"
    r"réservé(?:e|s|es)?\s+(?:uniquement\s+|exclusivement\s+)?"
    r"(?:aux?|à|pour)\s+[^.!?\n]{3,160}", re.I
)


def reservation_notice(url):
    """Note d'accès réservé, lue sur la fiche et non déduite du nombre disponible."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; PersonalAvailabilityMonitor/1.0)"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for el in soup(["script", "style", "noscript", "footer", "nav"]):
            el.decompose()
        # Les restrictions sont en tête de la fiche. Ne pas scanner les témoignages,
        # fiches voisines ou le texte générique en bas de page.
        main = soup.select_one("main") or soup.body or soup
        text = main.get_text(" ", strip=True)
        heading = main.find("h1")
        if heading:
            # Le bandeau d'accès réservé peut se trouver avant le titre.
            pos = text.find(heading.get_text(" ", strip=True))
            if pos >= 0:
                text = text[max(0, pos - 500):pos + 1200]
        else:
            text = text[:1800]
        match = RESTRICTION.search(text)
        if match:
            return "🔒 Accès réservé : " + match.group(0).strip().rstrip(" ,;:")
        # L'absence de mention sur la fiche ne garantit pas une éligibilité universelle.
        return "ℹ️ Aucune restriction spécifique détectée sur la fiche"
    except requests.RequestException as exc:
        print(f"Impossible de vérifier les restrictions pour {url}: {exc}")
        return "⚠️ Conditions d'accès non vérifiées"


def is_young_active(key, name):
    text = (key + " " + name).lower()
    return "jeunes-actifs" in text or "jeune-actif-" in text or "jeunes actifs" in text


def scan():
    r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (compatible; PersonalAvailabilityMonitor/1.0)"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    found = {}
    for a in soup.select("a[href]"):
        href = urljoin(URL, a["href"]).split("#")[0]
        parsed = urlparse(href)
        if parsed.netloc not in ("arpej.fr", "www.arpej.fr"):
            continue
        key = parsed.path.rstrip("/")
        if not key.startswith("/fr/residence/"):
            continue
        name = a.get_text(" ", strip=True)
        if not (3 <= len(name) <= 110):
            continue
        if not is_young_active(key, name):
            continue
        if key not in IDF:
            # Fail closed: unknown residences require geographic verification,
            # rather than possibly notifying for another region.
            print(f"A verifier (residence inconnue du referentiel IDF): {name} {href}")
            continue
        parent = a
        availability = None
        for _ in range(5):
            parent = parent.parent
            if parent is None:
                break
            content = parent.get_text(" ", strip=True)
            if len(content) > 700:
                break
            matches = AVAIL.findall(content)
            if len(matches) == 1:
                availability = int(matches[0])
                break
            if COMPLETE.search(content) and not matches:
                availability = 0
                break
        if availability is not None:
            found[key] = {"name": name, "url": href, "available": availability}
    if not found:
        raise RuntimeError("Aucune residence jeunes actifs IDF detectee. Verifier le HTML et les filtres.")
    return found


def notify(items):
    if not items:
        return
    if not WEBHOOK:
        raise RuntimeError("DISCORD_WEBHOOK_URL manquant")
    for item, before in items:
        notice = reservation_notice(item["url"])
        desc = f"**{item['name']}**\n{before} → **{item['available']} logement(s) disponible(s)**\n{notice}\n{item['url']}"
        r = requests.post(WEBHOOK, json={"content": "🏠 ARPEJ — jeune actif / Île-de-France\n" + desc,
                                           "allowed_mentions": {"parse": []}}, timeout=20)
        r.raise_for_status()


def main():
    current = scan()
    print(f"{len(current)} residences IDF jeunes actifs detectees; {sum(v['available'] > 0 for v in current.values())} avec disponibilites.")
    if not STATE.exists():
        STATE.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n")
        print("Initialisation du filtre : pas de notification.")
        return
    previous = json.loads(STATE.read_text())
    if len(current) < max(1, len(previous) // 2):
        raise RuntimeError("Scan incomplet, historique conserve.")
    changed = [(v, previous.get(k, {}).get("available", 0)) for k, v in current.items()
               if v["available"] > previous.get(k, {}).get("available", 0)]
    notify(changed)
    previous.update(current)
    STATE.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(changed)} notification(s).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERREUR : {exc}", file=sys.stderr)
        sys.exit(1)
