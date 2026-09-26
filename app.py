import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for, jsonify

DATABASE_URL = os.environ.get("DATABASE_URL") or "postgresql://postgres.eplaexjlmipvedfhwimk:2uMkgSfzLP.BAsq@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"

if DATABASE_URL:
    import psycopg2
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def get_db_connection():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    else:
        import sqlite3
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn

app = Flask(__name__)
CACHE_FILE = "images_cache.json"

KNOWN_RARITIES = [
    "Quarter Century Secret Rare", "Prismatic Secret Rare", "Extra Secret Rare",
    "Gold Secret Rare", "Secret Rare", "Premium Gold Rare", "Collector's Rare",
    "Ultimate Rare", "Ultra Rare", "Super Rare", "Normal Parallel Rare",
    "Normal Parallel", "Starfoil Rare", "Mosaic Rare", "Shatterfoil Rare",
    "Holographic Rare", "Ghost Rare", "Common", "Rare"
]

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    if DATABASE_URL:
        c.execute('''CREATE TABLE IF NOT EXISTS sets (
                        code TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        url TEXT NOT NULL,
                        release_date DATE
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS cards (
                        id SERIAL PRIMARY KEY,
                        set_code TEXT REFERENCES sets(code),
                        card_code TEXT,
                        name TEXT,
                        image_url TEXT
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS card_rarities (
                        id SERIAL PRIMARY KEY,
                        card_id INTEGER REFERENCES cards(id),
                        rarity_name TEXT,
                        quantity INTEGER DEFAULT 0
                    )''')
    else:
        c.execute('''CREATE TABLE IF NOT EXISTS sets (
                        code TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        url TEXT NOT NULL,
                        release_date TEXT
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS cards (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        set_code TEXT,
                        card_code TEXT,
                        name TEXT,
                        image_url TEXT,
                        FOREIGN KEY(set_code) REFERENCES sets(code)
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS card_rarities (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        card_id INTEGER,
                        rarity_name TEXT,
                        quantity INTEGER DEFAULT 0,
                        FOREIGN KEY(card_id) REFERENCES cards(id)
                    )''')
    conn.commit()
    conn.close()

with app.app_context():
    init_db()

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=4, ensure_ascii=False)

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

def clean_card_name_for_db(name):
    if not name: return ""
    clean = re.sub(r'[«»“”]', '"', name)
    clean = clean.strip(' "\' \t\r\n')
    if clean.lower().replace('"', '') == 'maxx c':
        return 'Maxx "C"'
    return clean

def clean_card_name_for_api(name):
    if not name: return ""
    clean = re.sub(r'\s*\([^)]*\)', '', name)
    clean = re.sub(r'[«»“”]', '"', clean)
    clean = clean.strip(' "\' \t\r\n')
    if clean.lower().replace('"', '') == 'maxx c':
        return 'Maxx "C"'
    return clean

def parse_rarities(rarity_str):
    if not rarity_str: return ["Common"]
    found = []
    text = rarity_str
    for r in sorted(KNOWN_RARITIES, key=len, reverse=True):
        if r in text:
            found.append(r)
            text = text.replace(r, '')
    return found if found else ["Common"]

def fetch_card_image(card_name, card_code, cache):
    default_back = "https://images.ygoprodeck.com/images/cards/back_high.jpg"
    api_name = clean_card_name_for_api(card_name)
    cache_key = f"{card_code}_{card_name}"
    if cache_key in cache and cache[cache_key] != default_back:
        return cache[cache_key]

    is_alt = "alternate" in card_name.lower() or "alt" in card_name.lower()
    api_url = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?name={requests.utils.quote(api_name)}"
    
    try:
        res = requests.get(api_url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if 'data' in data and len(data['data']) > 0:
                card_images = data['data'][0]['card_images']
                img_url = card_images[1]['image_url'] if (is_alt and len(card_images) > 1) else card_images[0]['image_url']
                cache[cache_key] = img_url
                return img_url
    except Exception as e:
        print(f"Erreur image: {e}", flush=True)

    cache[cache_key] = default_back
    return default_back

from datetime import datetime

from datetime import datetime

def extract_release_date(soup, set_code):
    """ Extrait la date de sortie exacte selon la région à partir de l'infobox Yugipedia """
    lang = set_code.split('-')[-1] if '-' in set_code else ''
    if lang == 'K':
        lang = 'KR'
    
    # Association entre le suffixe du set et le libellé Yugipedia
    region_map = {
        'FR': ['French', 'Europe', 'European'],
        'KR': ['Korean', 'South Korea'],
        'EN': ['English', 'North America', 'Worldwide', 'English (TCG)'],
        'JP': ['Japanese', 'Japan']
    }
    
    target_labels = region_map.get(lang, ['English', 'Worldwide', 'Japanese'])
    
    # 1. Chercher la section "Release dates" dans les tableaux
    for tr in soup.find_all('tr'):
        # On regarde s'il y a une étiquette de région (ex: Korean, Japanese, French)
        header = tr.find(['th', 'td'])
        if header:
            htext = header.text.strip()
            
            # Vérifier si l'étiquette correspond à la langue ciblée
            for label in target_labels:
                if label.lower() in htext.lower():
                    td = tr.find_all(['td', 'th'])[-1]
                    if td:
                        date_text = td.text.strip()
                        # Extraire la date du type "August 7, 2024" ou "7 August 2024"
                        m = re.search(r'([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})', date_text)
                        if m:
                            d_clean = m.group(1).replace(',', '')
                            for fmt in ("%B %d %Y", "%d %B %Y"):
                                try:
                                    return datetime.strptime(d_clean, fmt).strftime("%Y-%m-%d")
                                except ValueError:
                                    pass

    # 2. Fallback : si la région exacte n'est pas précisée, attraper la toute première date trouvée sous Release dates
    for tr in soup.find_all('tr'):
        text = tr.get_text(separator=' ')
        if 'release' in text.lower():
            m = re.search(r'([A-Za-z]+\s+\d{1,2},\s*\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})', text)
            if m:
                d_clean = m.group(1).replace(',', '')
                for fmt in ("%B %d %Y", "%d %B %Y"):
                    try:
                        return datetime.strptime(d_clean, fmt).strftime("%Y-%m-%d")
                    except ValueError:
                        pass

    return "1970-01-01"

@app.route('/')
def dashboard():
    conn = get_db_connection()
    c = conn.cursor()
    # Tri par date de sortie chronologique
    c.execute("SELECT code, name, release_date FROM sets ORDER BY release_date ASC, code ASC")
    sets_data = c.fetchall()

    sets_by_lang = {'fr': [], 'en': [], 'kr': []}

    for row in sets_data:
        code, name, rel_date = row[0], row[1], row[2]
        c.execute("SELECT COUNT(DISTINCT card_code) FROM cards WHERE set_code = %s" if DATABASE_URL else "SELECT COUNT(DISTINCT card_code) FROM cards WHERE set_code = ?", (code,))
        total = c.fetchone()[0]

        query_owned = '''SELECT COUNT(DISTINCT c.card_code) 
                         FROM cards c 
                         JOIN card_rarities r ON c.id = r.card_id 
                         WHERE c.set_code = %s AND r.quantity > 0''' if DATABASE_URL else '''SELECT COUNT(DISTINCT c.card_code) 
                         FROM cards c 
                         JOIN card_rarities r ON c.id = r.card_id 
                         WHERE c.set_code = ? AND r.quantity > 0'''
        c.execute(query_owned, (code,))
        owned = c.fetchone()[0]

        pct = round((owned / total * 100), 2) if total > 0 else 0
        set_item = {'code': code, 'name': name, 'total': total, 'owned': owned, 'pct': pct, 'date': rel_date}

        # Dispatch selon la langue (-FR, -EN, -KR ou par défaut -EN)
        if code.endswith('-FR'):
            sets_by_lang['fr'].append(set_item)
        elif code.endswith('-KR') or code.endswith('-K'):
            sets_by_lang['kr'].append(set_item)
        else:
            sets_by_lang['en'].append(set_item)

    conn.close()
    return render_template('dashboard.html', sets=sets_by_lang)

@app.route('/set/<set_code>')
def view_set(set_code):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT name FROM sets WHERE code = %s" if DATABASE_URL else "SELECT name FROM sets WHERE code = ?", (set_code,))
    set_info = c.fetchone()
    if not set_info:
        conn.close()
        return "Set Introuvable", 404

    query_cards_with_rarities = '''
        SELECT 
            c.id, c.card_code, c.name, c.image_url,
            r.id AS rarity_id, r.rarity_name, r.quantity
        FROM cards c
        LEFT JOIN card_rarities r ON c.id = r.card_id
        WHERE c.set_code = %s
        ORDER BY c.id ASC
    ''' if DATABASE_URL else '''
        SELECT 
            c.id, c.card_code, c.name, c.image_url,
            r.id AS rarity_id, r.rarity_name, r.quantity
        FROM cards c
        LEFT JOIN card_rarities r ON c.id = r.card_id
        WHERE c.set_code = ?
        ORDER BY c.id ASC
    '''
    c.execute(query_cards_with_rarities, (set_code,))
    rows = c.fetchall()

    c.execute("SELECT COUNT(DISTINCT card_code) FROM cards WHERE set_code = %s" if DATABASE_URL else "SELECT COUNT(DISTINCT card_code) FROM cards WHERE set_code = ?", (set_code,))
    total_unique_codes = c.fetchone()[0]

    query_owned = '''SELECT COUNT(DISTINCT c.card_code) 
                     FROM cards c 
                     JOIN card_rarities r ON c.id = r.card_id 
                     WHERE c.set_code = %s AND r.quantity > 0''' if DATABASE_URL else '''SELECT COUNT(DISTINCT c.card_code) 
                     FROM cards c 
                     JOIN card_rarities r ON c.id = r.card_id 
                     WHERE c.set_code = ? AND r.quantity > 0'''
    c.execute(query_owned, (set_code,))
    owned_unique_codes = c.fetchone()[0]
    conn.close()

    cards_dict = {}
    for row in rows:
        card_id, card_code, raw_name, img_url, rarity_id, rarity_name, qty = row
        if card_id not in cards_dict:
            is_alt = "alternate" in raw_name.lower() or "alt" in raw_name.lower()
            cards_dict[card_id] = {
                'id': card_id,
                'code': card_code,
                'name': clean_card_name_for_api(raw_name),
                'is_alt': is_alt,
                'img_url': img_url,
                'rarities': [],
                'owned': False
            }
        
        if rarity_id:
            cards_dict[card_id]['rarities'].append({'id': rarity_id, 'rarity': rarity_name, 'qty': qty})
            if qty > 0: cards_dict[card_id]['owned'] = True

    cards_data = list(cards_dict.values())
    pct = round((owned_unique_codes / total_unique_codes * 100), 2) if total_unique_codes > 0 else 0

    return render_template('set_view.html', set_code=set_code, set_name=set_info[0], 
                           cards=cards_data, total=total_unique_codes, owned=owned_unique_codes, pct=pct)

@app.route('/api/update_qty', methods=['POST'])
def update_qty():
    data = request.json
    rarity_id, delta = data.get('rarity_id'), data.get('delta')
    conn = get_db_connection()
    c = conn.cursor()
    if DATABASE_URL:
        c.execute("UPDATE card_rarities SET quantity = GREATEST(0, quantity + %s) WHERE id = %s", (delta, rarity_id))
    else:
        c.execute("UPDATE card_rarities SET quantity = MAX(0, quantity + ?) WHERE id = ?", (delta, rarity_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/add_set', methods=['POST'])
def add_set():
    set_code = request.form['set_code'].upper()
    set_name = request.form['set_name']
    url = request.form['url']

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return redirect(url_for('dashboard'))

    soup = BeautifulSoup(response.text, 'html.parser')
    release_date = extract_release_date(soup, set_code)
    
    conn = get_db_connection()
    c = conn.cursor()
    if DATABASE_URL:
        c.execute("INSERT INTO sets (code, name, url, release_date) VALUES (%s, %s, %s, %s) ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, url = EXCLUDED.url, release_date = EXCLUDED.release_date", (set_code, set_name, url, release_date))
    else:
        c.execute("INSERT OR REPLACE INTO sets (code, name, url, release_date) VALUES (?, ?, ?, ?)", (set_code, set_name, url, release_date))
    conn.commit()
    conn.close()

    cache = load_cache()
    raw_cards = []
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        card_inserted = False
        for row in rows[1:]:
            cols = row.find_all(['td', 'th'])
            if len(cols) >= 4:
                code = cols[0].text.strip()
                name = clean_card_name_for_db(cols[1].get_text(separator=' '))
                rarity_raw = clean_text(cols[3].get_text(separator=' '))
                if code and re.match(r'^[A-Z0-9]+-[A-Z0-9]+$', code):
                    card_inserted = True
                    raw_cards.append({'code': code, 'name': name, 'rarity_raw': rarity_raw})
        if card_inserted: break

    conn = get_db_connection()
    c = conn.cursor()
    for card in raw_cards:
        code, name, rarity_raw = card['code'], card['name'], card['rarity_raw']
        img_url = fetch_card_image(name, code, cache)

        if DATABASE_URL:
            c.execute("INSERT INTO cards (set_code, card_code, name, image_url) VALUES (%s, %s, %s, %s) RETURNING id", (set_code, code, name, img_url))
            card_id = c.fetchone()[0]
        else:
            c.execute("INSERT INTO cards (set_code, card_code, name, image_url) VALUES (?, ?, ?, ?)", (set_code, code, name, img_url))
            card_id = c.lastrowid

        rarities = parse_rarities(rarity_raw)
        for r in rarities:
            if DATABASE_URL:
                c.execute("INSERT INTO card_rarities (card_id, rarity_name, quantity) VALUES (%s, %s, 0)", (card_id, r))
            else:
                c.execute("INSERT INTO card_rarities (card_id, rarity_name, quantity) VALUES (?, ?, 0)", (card_id, r))
        time.sleep(0.05)

    save_cache(cache)
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)