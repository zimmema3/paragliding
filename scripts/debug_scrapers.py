import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests, bazar_watcher.scrapers as s, re
s._session = requests.Session()
s._session.headers.update(s.HEADERS)

print("=== BAZOS structure analysis ===")
soup = s._soup('https://sport.bazos.cz/inzeraty/paragliding-kridlo/')
ceny = soup.select('.inzeratycena, .cena')
print('cena elements:', len(ceny))
for c in ceny[:5]:
    print(' ', repr(c.get_text(' ',strip=True)[:100]))

for sel in ['table.inzerat', 'div.inzeraty', 'div.inzerat', 'tr.inzeratyflex', 'div.inzeratyflex', 'div.inzeratynadpis']:
    el = soup.select(sel)
    print(f' {sel}: {len(el)}')

divs = soup.select('div.inzeratynadpis')
if divs:
    parent = divs[0].find_parent()
    print('Parent tag:', parent.name if parent else None, 'class:', parent.get('class') if parent else None)
    print('Parent text:', repr(parent.get_text(' ',strip=True)[:400] if parent else ''))
    grandparent = parent.find_parent() if parent else None
    if grandparent:
        print('Grandparent:', grandparent.name, grandparent.get('class'))
        print('GP text:', repr(grandparent.get_text(' ',strip=True)[:500]))

print("\n=== FLUGSPORT.DE ===")
soup2 = s._soup('https://www.flugsport.de/flugsportladen/gebrauchtschirme.html')
if soup2:
    cards = soup2.select('article, .product, .product-item, li.product, .item, tr')
    print('cards:', len(cards))
    # Look for any price-like text
    prices = soup2.select('.price, .cena, [class*=price]')
    print('price elems:', len(prices))
    for p in prices[:5]:
        print(' ', repr(p.get_text(' ',strip=True)[:100]))
    # Body text scan
    body_txt = soup2.get_text(' ', strip=True)
    eur_matches = re.findall(r'\d[\d.,\s]*\s*(?:€|EUR)', body_txt)[:10]
    print('EUR matches in body:', eur_matches)
