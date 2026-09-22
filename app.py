import os
import re
import json
import sqlite3
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, redirect, url_for

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

app = Flask(__name__)
DB_FILE = "database.db"
CACHE_FILE = "images_cache.json"

def init_db():
    """Initialise la base de données SQLite."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS sets (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL
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
    text = re.sub(r'["«»]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def clean_card_name_for_api(name):
    """
    Conserve les guillemets officiels (ex: Gigantic "Champion" Sargas)
    mais retire le bloc de variante entre parenthèses (ex: (alternate artwork)).
    """
    clean = re.sub(r'\s*\([^)]*\)', '', name)
    clean = re.sub(r'[«»“”]', '"', clean)
    return re.sub(r'\s+', ' ', clean).strip()

def parse_rarities(rarity_str):
    if not rarity_str:
        return ["Common"]
    
    raw_list = re.split(r'[/,\n]', rarity_str)
    rarities = []
    
    for r in raw_list:
        cleaned = clean_text(r)
        sub_rarities = re.findall(
            r'(Prismatic Secret Rare|Secret Rare|Ultra Rare|Super Rare|Normal Parallel Rare|Normal Parallel|Ultimate Rare|Collector\'s Rare|Quarter Century Secret Rare|Common)', 
            cleaned
        )
        
        if sub_rarities:
            for sr in sub_rarities:
                if sr not in rarities:
                    rarities.append(sr)
        elif cleaned and cleaned not in rarities:
            rarities.append(cleaned)

    return rarities if rarities else ["Common"]

def fetch_card_image(card_name, card_code, cache):
    default_back = "https://images.ygoprodeck.com/images/cards/back_high.jpg"
    cache_key = f"{card_code}_{card_name}"

    if cache_key in cache and cache[cache_key] != default_back:
        return cache[cache_key]

    is_alt = "alternate" in card_name.lower() or "alt" in card_name.lower()
    search_name = clean_card_name_for_api(card_name)

    api_url = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?name={requests.utils.quote(search_name)}"
    
    try:
        res = requests.get(api_url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if 'data' in data and len(data['data']) > 0:
                card_images = data['data'][0]['card_images']
                if is_alt and len(card_images) > 1:
                    img_url = card_images[1]['image_url']
                else:
                    img_url = card_images[0]['image_url']
                
                cache[cache_key] = img_url
                return img_url

        fuzzy_name = re.sub(r'["«»“”]', '', search_name)
        api_url_fuzzy = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?fname={requests.utils.quote(fuzzy_name)}"
        res_fuzzy = requests.get(api_url_fuzzy, timeout=5)
        
        if res_fuzzy.status_code == 200:
            data = res_fuzzy.json()
            if 'data' in data and len(data['data']) > 0:
                card_images = data['data'][0]['card_images']
                if is_alt and len(card_images) > 1:
                    img_url = card_images[1]['image_url']
                else:
                    img_url = card_images[0]['image_url']
                
                cache[cache_key] = img_url
                return img_url

    except Exception as e:
        print(f"Erreur image pour '{search_name}': {e}")

    cache[cache_key] = default_back
    return default_back

def import_set_from_yugipedia(set_code, set_name, url):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO sets (code, name, url) VALUES (?, ?, ?)", (set_code, set_name, url))
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        conn.close()
        return False

    soup = BeautifulSoup(response.text, 'html.parser')
    cache = load_cache()

    raw_cards = []
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        card_inserted = False
        for row in rows[1:]:
            cols = row.find_all(['td', 'th'])
            if len(cols) >= 4:
                code = cols[0].text.strip()
                name = clean_text(cols[1].get_text(separator=' '))
                rarity_raw = clean_text(cols[3].get_text(separator=' '))

                if code and re.match(r'^[A-Z0-9]+-[A-Z0-9]+$', code):
                    card_inserted = True
                    raw_cards.append({'code': code, 'name': name, 'rarity_raw': rarity_raw})
        if card_inserted:
            break

    total_cards = len(raw_cards)
    print(f"\n[IMPORTATION] Set {set_code} ({total_cards} cartes à traiter)")

    iterator = enumerate(raw_cards, 1)
    if HAS_TQDM:
        iterator = enumerate(tqdm(raw_cards, desc=f"Importation {set_code}", unit="carte"), 1)

    for idx, card in iterator:
        code = card['code']
        name = card['name']
        rarity_raw = card['rarity_raw']

        if not HAS_TQDM:
            print(f"  [{idx}/{total_cards}] Traitement de {code} - {name}...")

        img_url = fetch_card_image(name, code, cache)

        c.execute("INSERT INTO cards (set_code, card_code, name, image_url) VALUES (?, ?, ?, ?)",
                  (set_code, code, name, img_url))
        card_id = c.lastrowid

        rarities = parse_rarities(rarity_raw)
        for r in rarities:
            c.execute("INSERT INTO card_rarities (card_id, rarity_name, quantity) VALUES (?, ?, 0)",
                      (card_id, r))
        
        time.sleep(0.1)

    save_cache(cache)
    conn.commit()
    conn.close()
    print(f"[SUCCÈS] Importation du set {set_code} terminée !\n")
    return True

@app.route('/')
def dashboard():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT code, name FROM sets")
    sets_data = c.fetchall()

    dashboard_stats = []
    for code, name in sets_data:
        c.execute("SELECT COUNT(DISTINCT card_code) FROM cards WHERE set_code = ?", (code,))
        total = c.fetchone()[0]

        c.execute('''SELECT COUNT(DISTINCT c.card_code) 
                     FROM cards c 
                     JOIN card_rarities r ON c.id = r.card_id 
                     WHERE c.set_code = ? AND r.quantity > 0''', (code,))
        owned = c.fetchone()[0]

        pct = round((owned / total * 100), 2) if total > 0 else 0
        dashboard_stats.append({'code': code, 'name': name, 'total': total, 'owned': owned, 'pct': pct})

    conn.close()
    return render_template('dashboard.html', sets=dashboard_stats)

@app.route('/set/<set_code>')
def view_set(set_code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("SELECT name FROM sets WHERE code = ?", (set_code,))
    set_info = c.fetchone()
    if not set_info:
        conn.close()
        return "Set Introuvable", 404

    c.execute("SELECT id, card_code, name, image_url FROM cards WHERE set_code = ?", (set_code,))
    cards = c.fetchall()

    c.execute("SELECT COUNT(DISTINCT card_code) FROM cards WHERE set_code = ?", (set_code,))
    total_unique_codes = c.fetchone()[0]

    c.execute('''SELECT COUNT(DISTINCT c.card_code) 
                 FROM cards c 
                 JOIN card_rarities r ON c.id = r.card_id 
                 WHERE c.set_code = ? AND r.quantity > 0''', (set_code,))
    owned_unique_codes = c.fetchone()[0]

    cards_data = []
    for card_id, card_code, raw_name, img_url in cards:
        c.execute("SELECT id, rarity_name, quantity FROM card_rarities WHERE card_id = ?", (card_id,))
        rarities = [{'id': row[0], 'rarity': row[1], 'qty': row[2]} for row in c.fetchall()]
        
        is_owned = any(r['qty'] > 0 for r in rarities)

        is_alt = "alternate" in raw_name.lower() or "alt" in raw_name.lower()
        clean_card_name = clean_card_name_for_api(raw_name)

        cards_data.append({
            'id': card_id,
            'code': card_code,
            'name': clean_card_name,
            'is_alt': is_alt,
            'img_url': img_url,
            'rarities': rarities,
            'owned': is_owned
        })

    pct = round((owned_unique_codes / total_unique_codes * 100), 2) if total_unique_codes > 0 else 0
    conn.close()

    return render_template('set_view.html', set_code=set_code, set_name=set_info[0], 
                           cards=cards_data, total=total_unique_codes, owned=owned_unique_codes, pct=pct)

@app.route('/api/update_qty', methods=['POST'])
def update_qty():
    data = request.json
    rarity_id = data.get('rarity_id')
    delta = data.get('delta')

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE card_rarities SET quantity = MAX(0, quantity + ?) WHERE id = ?", (delta, rarity_id))
    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})

@app.route('/add_set', methods=['POST'])
def add_set():
    set_code = request.form['set_code'].upper()
    set_name = request.form['set_name']
    url = request.form['url']
    
    import_set_from_yugipedia(set_code, set_name, url)
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)