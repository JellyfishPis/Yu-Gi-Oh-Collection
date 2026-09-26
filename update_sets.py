import os
import re
import requests
from bs4 import BeautifulSoup
from app import get_db_connection, DATABASE_URL, extract_release_date

def get_main_set_url(url):
    if "Set_Card_Lists:" in url:
        main_part = url.split("Set_Card_Lists:")[1]
        # Supprime _(OCG-KR), _(OCG-K), _(TCG-EN), etc.
        main_part = re.sub(r'_\([A-Z0-9\-]+\)$', '', main_part)
        return f"https://yugipedia.com/wiki/{main_part}"
    return url

def update_existing_sets():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT code, url FROM sets")
    sets = c.fetchall()
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    print("Début de l'extraction des dates de sortie...")
    
    for set_code, url in sets:
        main_url = get_main_set_url(url)
        print(f"Analyse de {set_code} ({main_url})...")
        
        response = requests.get(main_url, headers=headers)
        if response.status_code != 200:
            # Si redirection échouée, on tente l'URL d'origine
            response = requests.get(url, headers=headers)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            release_date = extract_release_date(soup, set_code)
            
            if DATABASE_URL:
                c.execute("UPDATE sets SET release_date = %s WHERE code = %s", (release_date, set_code))
            else:
                c.execute("UPDATE sets SET release_date = ? WHERE code = ?", (release_date, set_code))
                
            print(f" Set {set_code} -> Date : {release_date}")
        else:
            print(f" Échec pour {set_code}")

    conn.commit()
    conn.close()
    print("\n Toutes les dates ont été mises à jour !")

if __name__ == '__main__':
    update_existing_sets()