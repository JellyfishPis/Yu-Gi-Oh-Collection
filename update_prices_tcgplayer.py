import os
import re
import time
import psycopg2
import sqlite3
from playwright.sync_api import sync_playwright

DATABASE_URL = os.environ.get("DATABASE_URL") or "postgresql://postgres.eplaexjlmipvedfhwimk:2uMkgSfzLP.BAsq@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"

def get_db_connection():
    if DATABASE_URL and "postgresql" in DATABASE_URL:
        db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1) if DATABASE_URL.startswith("postgres://") else DATABASE_URL
        return psycopg2.connect(db_url, sslmode='require')
    else:
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        return conn

def scrape_cards_capital():
    base_url = "https://www.cards-capital.com/1168-cartes-boite-du-25e-anniversaire-les-miroirs-du-duel-mp24-a-l-unite"
    cc_prices = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        
        page_num = 1
        previous_total = 0
        
        while True:
            # Utilisation du paramètre exact de pagination du site
            url = f"{base_url}?p={page_num}"
            print(f"Chargement de la page {page_num}...")
            
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            
            product_elements = page.query_selector_all("li, div.product-container, div.product-miniature, div.product")
            products_found = 0
            
            for prod in product_elements:
                text = prod.inner_text().strip()
                
                if "MP24-FR" in text:
                    code_match = re.search(r'(MP24-FR\d{3})', text)
                    price_match = re.search(r'(\d+[,.]\d{2})\s*€', text)
                    
                    if code_match and price_match:
                        card_code = code_match.group(1)
                        clean_price = price_match.group(1).replace(',', '.')
                        
                        cc_prices[card_code] = float(clean_price)
                        products_found += 1
            
            current_total = len(cc_prices)
            print(f"Page {page_num} : {products_found} produits extraits. (Total unique: {current_total})")
            
            # Sécurité pour stopper la boucle infinie
            if current_total == previous_total:
                print("Le site renvoie la même page ou n'a plus de nouveaux produits. Fin du scraping.")
                break
                
            previous_total = current_total
            page_num += 1

        browser.close()
        
    return cc_prices

def update_db_with_cc_prices():
    cc_prices = scrape_cards_capital()
    
    if not cc_prices:
        print("Erreur : Aucun prix récupéré. Vérifie la fenêtre du navigateur pour voir s'il y a un Captcha à résoudre manuellement.")
        return

    conn = get_db_connection()
    c = conn.cursor()
    is_postgres = bool(DATABASE_URL and "postgresql" in DATABASE_URL)

    query = """
        SELECT r.id, c.card_code, r.rarity_name 
        FROM card_rarities r
        JOIN cards c ON r.card_id = c.id
        WHERE c.set_code LIKE 'MP24%'
    """
    c.execute(query)
    db_rarities = c.fetchall()

    for r_id, card_code, rarity_name in db_rarities:
        if card_code in cc_prices:
            price = cc_prices[card_code]
            if price > 0:
                upd = "UPDATE card_rarities SET price = %s WHERE id = %s" if is_postgres else "UPDATE card_rarities SET price = ? WHERE id = ?"
                c.execute(upd, (price, r_id))
                print(f"✔ {card_code} [{rarity_name}] -> {price:.2f} €")
        else:
            print(f"⚠️ Prix non trouvé sur Cards Capital pour {card_code}")

    conn.commit()
    conn.close()
    print("Mise à jour terminée avec succès !")

if __name__ == "__main__":
    update_db_with_cc_prices()