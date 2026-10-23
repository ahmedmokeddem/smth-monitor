import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

URL = 'https://www.arpej.fr/fr/nos-residences/?related_city=52524&iam=jeunes-actifs&show_if_full=true'
STATE = Path('state.json')
WEBHOOK = os.getenv('DISCORD_WEBHOOK_URL', '')
# Optional: matching text in residence URLs/names (case insensitive).
NAME_FILTER = os.getenv('NAME_FILTER', '').strip().lower()
AVAIL = re.compile(r'\b(\d+)\s+disponible(?:s)?\b', re.I)
COMPLETE = re.compile(r'\bcomplet(?:e|s|es)?\b', re.I)


def scan():
    response = requests.get(URL, timeout=30, headers={'User-Agent': 'Mozilla/5.0 (compatible; PersonalAvailabilityMonitor/1.0)'})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    found = {}
    for a in soup.select('a[href]'):
        href = urljoin(URL, a['href']).split('#')[0]
        if urlparse(href).netloc not in ('arpej.fr', 'www.arpej.fr'):
            continue
        name = a.get_text(' ', strip=True)
        if not 3 <= len(name) <= 110 or 'résidence' in name.lower() and len(name) < 12:
            continue
        if NAME_FILTER and NAME_FILTER not in (name + ' ' + href).lower():
            continue
        card = a
        availability = None
        for _ in range(5):
            card = card.parent
            if card is None:
                break
            txt = card.get_text(' ', strip=True)
            if len(txt) > 700:
                break
            matches = AVAIL.findall(txt)
            if len(matches) == 1:
                availability = int(matches[0]); break
            if COMPLETE.search(txt) and not matches:
                availability = 0; break
        if availability is not None:
            key = urlparse(href).path.rstrip('/')
            found[key] = {'name': name, 'url': href, 'available': availability}
    if not found:
        raise RuntimeError('Aucune disponibilité lisible dans le HTML. Le site a peut-être changé ou charge les cartes en JavaScript.')
    return found


def notify(announcements):
    if not announcements:
        return
    if not WEBHOOK:
        raise RuntimeError('DISCORD_WEBHOOK_URL manquant')
    for item, before in announcements:
        name = item['name']
        now = item['available']
        desc = f"**{name}**\n{before} → **{now} logement(s) disponible(s)**\n{item['url']}"
        response = requests.post(WEBHOOK, json={'content': '🏠 ARPEJ — nouvelle disponibilité\n' + desc, 'allowed_mentions': {'parse': []}}, timeout=20)
        response.raise_for_status()


def main():
    current = scan()
    print(f'{len(current)} résidences détectées, dont {sum(v["available"] > 0 for v in current.values())} disponibles.')
    if not STATE.exists():
        STATE.write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n')
        print('Initialisation : aucune notification envoyée.')
        return
    previous = json.loads(STATE.read_text())
    if len(current) < max(1, len(previous) // 2):
        raise RuntimeError('Scan anormalement incomplet : historique conservé.')
    changed = [(v, previous[k]['available'] if k in previous else 0) for k, v in current.items() if v['available'] > (previous.get(k, {}).get('available', 0))]
    # Send before writing state, so notification failures are retried.
    notify(changed)
    # Keep historical residences, including disappeared ones.
    previous.update(current)
    STATE.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + '\n')
    print(f'{len(changed)} notification(s).')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERREUR : {exc}', file=sys.stderr)
        sys.exit(1)
