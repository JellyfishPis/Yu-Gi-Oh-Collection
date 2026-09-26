import os
import re
import requests
from bs4 import BeautifulSoup
from app import get_db_connection, DATABASE_URL, parse_rarities, clean_text

def get_main_set_url(url):
    if "Set_Card_Lists:" in url:
        main_part = url.split("Set_Card_Lists:")[1]
        main_part = re.sub(r'_\([A-Z0-9\-]+\)$', '', main_part)
        return f"https://yugipedia.com/wiki/{main_part}"
    return url

def fix_all_rarities():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT code, url FROM sets")
    sets = c.fetchall()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    print("Début du remplissage propre des raretés...")
    
    for set_code, url in sets:
        main_url = get_main_set_url(url)
        print(f"\n--- Traitement du set : {set_code} ({main_url}) ---")
        
        response = requests.get(main_url, headers=headers)
        if response.status_code != 200:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                print(f" Impossible d'accéder à l'URL pour {set_code}")
                continue

        soup = BeautifulSoup(response.text, 'html.parser')
        
        table = soup.find('table', class_=re.compile(r'wikitable|grid', re.I))
        if not table:
            continue

        rows = table.find_all('tr')
        if not rows:
            continue

        # Détection dynamique des colonnes via les en-têtes (th)
        headers_text = [th.text.strip().lower() for th in rows[0].find_all(['th', 'td'])]
        code_idx, name_idx, rarity_idx = 0, 1, -1

        for i, h in enumerate(headers_text):
            if 'number' in h or 'code' in h: code_idx = i
            elif 'name' in h: name_idx = i
            elif 'rarity' in h: rarity_idx = i

        for row in rows[1:]:
            cols = row.find_all(['td', 'th'])
            if len(cols) <= max(code_idx, name_idx):
                continue

            code = cols[code_idx].text.strip()
            raw_name = clean_text(cols[name_idx].get_text(separator=' '))
            
            # Récupération de la rareté selon l'index détecté
            if rarity_idx != -1 and len(cols) > rarity_idx:
                rarity_raw = cols[rarity_idx].get_text(separator=' ')
            elif len(cols) >= 3:
                rarity_raw = cols[2].get_text(separator=' ')
            else:
                rarity_raw = "Common"

            if code and re.match(r'^[A-Z0-9]+-[A-Z0-9]+$', code):
                is_alt = "alternate" in raw_name.lower() or "alt" in raw_name.lower()
                
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
                    
                    # 1. Récupérer les raretés existantes
                    c.execute(
                        "SELECT rarity_name, quantity FROM card_rarities WHERE card_id = %s" if DATABASE_URL
                        else "SELECT rarity_name, quantity FROM card_rarities WHERE card_id = ?",
                        (target_id,)
                    )
                    existing = {r_name: qty for r_name, qty in c.fetchall()}

                    # 2. Insérer uniquement les nouvelles raretés manquantes
                    for r in expected_rarities:
                        if r not in existing:
                            if DATABASE_URL:
                                c.execute("INSERT INTO card_rarities (card_id, rarity_name, quantity) VALUES (%s, %s, 0)", (target_id, r))
                            else:
                                c.execute("INSERT INTO card_rarities (card_id, rarity_name, quantity) VALUES (?, ?, 0)", (target_id, r))
                            print(f" Ajouté : [{r}] pour {code}")

                    # 3. Supprimer la rareté Common par défaut SI une vraie rareté a été trouvée et que la quantité est 0
                    if len(expected_rarities) > 0 and "Common" not in expected_rarities and "Common" in existing and existing["Common"] == 0:
                        if DATABASE_URL:
                            c.execute("DELETE FROM card_rarities WHERE card_id = %s AND rarity_name = 'Common'", (target_id,))
                        else:
                            c.execute("DELETE FROM card_rarities WHERE card_id = ? AND rarity_name = 'Common'", (target_id,))

    conn.commit()
    conn.close()
    print("\n Reconstitution des raretés terminée avec succès !")

if __name__ == '__main__':
    fix_all_rarities()