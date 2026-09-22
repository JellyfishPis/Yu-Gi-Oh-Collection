import sqlite3
import requests
import json
import os
import re

DB_FILE = "database.db"
CACHE_FILE = "images_cache.json"

def clean_name_keep_quotes(name):
    """
    Retire les parenthèses de variante mais CONSERVE les guillemets.
    Exemple : 'Gigantic "Champion" Sargas (alternate art)' -> 'Gigantic "Champion" Sargas'
    """
    clean = re.sub(r'\s*\([^)]*\)', '', name)
    return re.sub(r'\s+', ' ', clean).strip()

def try_add_missing_quotes(name):
    """
    Tente de rajouter des guillemets sur des termes connus de Yu-Gi-Oh! 
    si Yugipedia les a nettoyés.
    """
    # Si c'est un mot court comme C (Sneaky "C", Maxx "C", etc.)
    name_with_c = re.sub(r'\bC\b', '"C"', name)
    if name_with_c != name:
        return name_with_c
    
    # Si le mot Champion n'a pas de guillemets
    name_with_champ = re.sub(r'\bChampion\b', '"Champion"', name)
    if name_with_champ != name:
        return name_with_champ

    return name

def fix_missing_images():
    if not os.path.exists(DB_FILE):
        print("Erreur : La base de données database.db n'existe pas.")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT id, card_code, name FROM cards WHERE image_url LIKE '%back_high.jpg%'")
    missing_cards = c.fetchall()

    total = len(missing_cards)
    if total == 0:
        print("Toutes les cartes ont déjà une illustration !")
        conn.close()
        return

    print(f"\n[RATTRAPAGE] {total} carte(s) sans illustration trouvée(s).\n")

    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            try: cache = json.load(f)
            except: cache = {}

    updated_count = 0

    for idx, (card_id, card_code, raw_name) in enumerate(missing_cards, 1):
        is_alt = "alternate" in raw_name.lower() or "alt" in raw_name.lower()
        
        # 1. Nom nettoyé sans parenthèses
        search_name = clean_name_keep_quotes(raw_name)
        new_url = None

        print(f"[{idx}/{total}] Recherche pour : {card_code} - {search_name}...")

        # Liste des variantes de noms à tester auprès de l'API
        name_variants = [
            search_name,
            try_add_missing_quotes(search_name),
            re.sub(r'["«»“”]', '', search_name) # Sans guillemets du tout
        ]

        # Supprimer les doublons dans la liste
        name_variants = list(dict.fromkeys(name_variants))

        for variant in name_variants:
            if new_url: break
            
            # Test 1 : recherche exacte name=
            api_url = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?name={requests.utils.quote(variant)}"
            try:
                res = requests.get(api_url, timeout=4)
                if res.status_code == 200:
                    data = res.json()
                    if 'data' in data and len(data['data']) > 0:
                        imgs = data['data'][0]['card_images']
                        new_url = imgs[1]['image_url'] if (is_alt and len(imgs) > 1) else imgs[0]['image_url']
                        break
            except Exception:
                pass

            # Test 2 : recherche partielle fname=
            api_url_fuzzy = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?fname={requests.utils.quote(variant)}"
            try:
                res_fuzzy = requests.get(api_url_fuzzy, timeout=4)
                if res_fuzzy.status_code == 200:
                    data = res_fuzzy.json()
                    if 'data' in data and len(data['data']) > 0:
                        imgs = data['data'][0]['card_images']
                        new_url = imgs[1]['image_url'] if (is_alt and len(imgs) > 1) else imgs[0]['image_url']
                        break
            except Exception:
                pass

        # Mise à jour en base SQLite
        if new_url and "back_high.jpg" not in new_url:
            c.execute("UPDATE cards SET image_url = ? WHERE id = ?", (new_url, card_id))
            cache[f"{card_code}_{raw_name}"] = new_url
            updated_count += 1
            print(f"   SUCCÈS -> Image trouvée : {new_url}")
        else:
            print(f"   ÉCHEC -> Toujours introuvable sur l'API.")

    conn.commit()
    conn.close()

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=4, ensure_ascii=False)

    print(f"\n[FIN] Terminé ! {updated_count}/{total} image(s) mise(s) à jour avec succès.\n")

if __name__ == "__main__":
    fix_missing_images()