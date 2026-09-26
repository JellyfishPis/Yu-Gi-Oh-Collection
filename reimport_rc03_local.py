import os
import re
import time
from bs4 import BeautifulSoup
from app import (
    get_db_connection, DATABASE_URL, parse_rarities,
    clean_card_name_for_db, fetch_card_image, load_cache, save_cache
)

def clean_and_reimport_from_html(set_code, html_filename):
    if not os.path.exists(html_filename):
        print(f"Erreur : le fichier {html_filename} n'existe pas dans le dossier.")
        return

    print(f"Lecture du fichier HTML local {html_filename}...")
    with open(html_filename, 'r', encoding='utf-8') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    tables = soup.find_all('table', class_=re.compile(r'wikitable|sortable'))

    raw_cards = []
    for table in tables:
        rows = table.find_all('tr')
        for row in rows[1:]:
            cols = row.find_all(['td', 'th'])
            if len(cols) >= 4:
                code = cols[0].text.strip().upper()
                name = clean_card_name_for_db(cols[1].get_text(separator=' '))
                rarity_raw = cols[3].get_text(separator=' ').strip()

                if code and re.match(r'^[A-Z0-9]+-K[R0-9]+$', code):
                    raw_cards.append({
                        'code': code,
                        'name': name,
                        'rarity_raw': rarity_raw
                    })

    if not raw_cards:
        print("Aucune carte trouvée dans le fichier HTML.")
        return

    print(f"--> {len(raw_cards)} cartes coréennes extraites.")

    # 1. Nettoyage BDD
    conn = get_db_connection()
    c = conn.cursor()

    query_del_rarities = """
        DELETE FROM card_rarities 
        WHERE card_id IN (SELECT id FROM cards WHERE set_code = %s)
    """ if DATABASE_URL else """
        DELETE FROM card_rarities 
        WHERE card_id IN (SELECT id FROM cards WHERE set_code = ?)
    """
    c.execute(query_del_rarities, (set_code,))

    query_del_cards = "DELETE FROM cards WHERE set_code = %s" if DATABASE_URL else "DELETE FROM cards WHERE set_code = ?"
    c.execute(query_del_cards, (set_code,))
    conn.commit()
    print("Anciennes cartes supprimées de la base de données.")

    # 2. Réinsertion propre des cartes et raretés
    cache = load_cache()
    inserted_count = 0

    for card in raw_cards:
        code, name, rarity_raw = card['code'], card['name'], card['rarity_raw']
        img_url = fetch_card_image(name, code, cache)

        if DATABASE_URL:
            c.execute(
                "INSERT INTO cards (set_code, card_code, name, image_url) VALUES (%s, %s, %s, %s) RETURNING id",
                (set_code, code, name, img_url)
            )
            card_id = c.fetchone()[0]
        else:
            c.execute(
                "INSERT INTO cards (set_code, card_code, name, image_url) VALUES (?, ?, ?, ?)",
                (set_code, code, name, img_url)
            )
            card_id = c.lastrowid

        rarities = parse_rarities(rarity_raw)
        for r in rarities:
            if DATABASE_URL:
                c.execute("INSERT INTO card_rarities (card_id, rarity_name, quantity, price) VALUES (%s, %s, 0, 0.0)", (card_id, r))
            else:
                c.execute("INSERT INTO card_rarities (card_id, rarity_name, quantity, price) VALUES (?, ?, 0, 0.0)", (card_id, r))

        inserted_count += 1
        time.sleep(0.05)

    save_cache(cache)
    conn.commit()
    conn.close()

    print(f"\nTerminé ! {inserted_count} cartes coréennes réinsérées avec succès.")

if __name__ == '__main__':
    clean_and_reimport_from_html("RC03-KR", "fandom_rc03.html")