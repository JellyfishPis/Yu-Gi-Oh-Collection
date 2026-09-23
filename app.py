import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for, jsonify

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    import psycopg2
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def get_db_connection():
    if DATABASE_URL:
        # Connexion à distance (Supabase / PostgreSQL)
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    else:
        # Connexion locale (SQLite)
        import sqlite3
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn

app = Flask(__name__)
CACHE_FILE = "images_cache.json"

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    if DATABASE_URL:
        c.execute('''CREATE TABLE IF NOT EXISTS sets (
                        code TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        url TEXT NOT NULL
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
                if sr not in rarities: rarities.append(sr)
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
                img_url = card_images[1]['image_url'] if (is_alt and len(card_images) > 1) else card_images[0]['image_url']
                cache[cache_key] = img_url
                return img_url
    except Exception as e:
        print(f"Erreur image: {e}")

    cache[cache_key] = default_back
    return default_back

@app.route('/')
def dashboard():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT code, name FROM sets")
    sets_data = c.fetchall()

    dashboard_stats = []
    for row in sets_data:
        code, name = row[0], row[1]
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
        dashboard_stats.append({'code': code, 'name': name, 'total': total, 'owned': owned, 'pct': pct})

    conn.close()
    return render_template('dashboard.html', sets=dashboard_stats)

@app.route('/set/<set_code>')
def view_set(set_code):
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT name FROM sets WHERE code = %s" if DATABASE_URL else "SELECT name FROM sets WHERE code = ?", (set_code,))
    set_info = c.fetchone()
    if not set_info:
        conn.close()
        return "Set Introuvable", 404

    c.execute("SELECT id, card_code, name, image_url FROM cards WHERE set_code = %s" if DATABASE_URL else "SELECT id, card_code, name, image_url FROM cards WHERE set_code = ?", (set_code,))
    cards = c.fetchall()

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

    cards_data = []
    for card in cards:
        card_id, card_code, raw_name, img_url = card[0], card[1], card[2], card[3]
        c.execute("SELECT id, rarity_name, quantity FROM card_rarities WHERE card_id = %s" if DATABASE_URL else "SELECT id, rarity_name, quantity FROM card_rarities WHERE card_id = ?", (card_id,))
        rarities = [{'id': r[0], 'rarity': r[1], 'qty': r[2]} for r in c.fetchall()]
        
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
    
    conn = get_db_connection()
    c = conn.cursor()
    if DATABASE_URL:
        c.execute("INSERT INTO sets (code, name, url) VALUES (%s, %s, %s) ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, url = EXCLUDED.url", (set_code, set_name, url))
    else:
        c.execute("INSERT OR REPLACE INTO sets (code, name, url) VALUES (?, ?, ?)", (set_code, set_name, url))
    conn.commit()
    conn.close()

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return redirect(url_for('dashboard'))

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

    conn = get_db_connection()
    c = conn.cursor()
    for card in raw_cards:
        code = card['code']
        name = card['name']
        rarity_raw = card['rarity_raw']

        img_url = fetch_card_image(name, code, cache)

        if DATABASE_URL:
            c.execute("INSERT INTO cards (set_code, card_code, name, image_url) VALUES (%s, %s, %s, %s) RETURNING id",
                      (set_code, code, name, img_url))
            card_id = c.fetchone()[0]
        else:
            c.execute("INSERT INTO cards (set_code, card_code, name, image_url) VALUES (?, ?, ?, ?)",
                      (set_code, code, name, img_url))
            card_id = c.lastrowid

        rarities = parse_rarities(rarity_raw)
        for r in rarities:
            if DATABASE_URL:
                c.execute("INSERT INTO card_rarities (card_id, rarity_name, quantity) VALUES (%s, %s, 0)",
                          (card_id, r))
            else:
                c.execute("INSERT INTO card_rarities (card_id, rarity_name, quantity) VALUES (?, ?, 0)",
                          (card_id, r))
        time.sleep(0.05)

    save_cache(cache)
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)