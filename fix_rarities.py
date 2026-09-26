import os
import re
import requests
from bs4 import BeautifulSoup
from app import get_db_connection, DATABASE_URL, parse_rarities, clean_text

def fix_all_rarities():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT code, url FROM sets")
    sets = c.fetchall()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    print("Début du remplissage propre des raretés...")
    
    for set_code, url in sets:
        print(f"\n--- Traitement du set : {set_code} ---")
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f" Impossible d'accéder à l'URL pour {set_code}")
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            for row in rows[1:]:
                cols = row.find_all(['td', 'th'])
                if len(cols) >= 4:
                    code = cols[0].text.strip()
                    raw_name = clean_text(cols[1].get_text(separator=' '))
                    rarity_raw = cols[3].get_text(separator=' ')
                    
                    if code and re.match(r'^[A-Z0-9]+-[A-Z0-9]+$', code):
                        is_alt = "alternate" in raw_name.lower() or "alt" in raw_name.lower()
                        
                        # Requête corrigée avec les 2 paramètres (set_code et code)
                        c.execute(
                            "SELECT id, name FROM cards WHERE set_code = %s AND card_code = %s" if DATABASE_URL 
                            else "SELECT id, name FROM cards WHERE set_code = ? AND card_code = ?", 
                            (set_code, code)
                        )
                        card_rows = c.fetchall()
                        
                        target_id = None
                        if len(card_rows) == 1:
                            target_id = card_rows[0][0]
                        elif len(card_rows) > 1:
                            for cid, cname in card_rows:
                                cname_is_alt = "alternate" in cname.lower() or "alt" in cname.lower()
                                if is_alt == cname_is_alt:
                                    target_id = cid
                                    break

                        if target_id:
                            expected_rarities = parse_rarities(rarity_raw)
                            for r in expected_rarities:
                                if DATABASE_URL:
                                    c.execute("INSERT INTO card_rarities (card_id, rarity_name, quantity) VALUES (%s, %s, 0)", (target_id, r))
                                else:
                                    c.execute("INSERT INTO card_rarities (card_id, rarity_name, quantity) VALUES (?, ?, 0)", (target_id, r))
                                print(f" Ajouté : [{r}] pour {code} (ID: {target_id})")

    conn.commit()
    conn.close()
    print("\n Reconstitution des raretés terminée avec succès !")