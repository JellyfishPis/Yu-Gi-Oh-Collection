import re
import requests
from bs4 import BeautifulSoup
from app import get_db_connection, DATABASE_URL

def scrape_ktcg_all_pages(base_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cache-Control': 'no-cache'
    }
    
    extracted_data = []
    page = 1

    while True:
        page_url = f"{base_url.rstrip('/')}/page/{page}/" if page > 1 else base_url
        print(f"Scraping page {page} : {page_url}")
        
        response = requests.get(page_url, headers=headers)
        if response.status_code != 200:
            print(f"  -> Statut HTTP {response.status_code}, arrêt.")
            break

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Sélectionne directement les cartes/produits de la grille WooCommerce
        products = soup.select('ul.products li.product, div.products div.product')
        if not products:
            # Fallback sur une recherche de balises li ou div avec la classe product
            products = soup.find_all(['li', 'div'], class_=re.compile(r'\bproduct\b'))

        if not products:
            print("  -> Aucun produit détecté dans le DOM.")
            break

        items_found = 0
        for product in products:
            # Recherche du titre du produit
            title_node = product.select_one('.woocommerce-loop-product__title, .product-title, h2, h3')
            if not title_node:
                continue

            full_title = title_node.get_text(strip=True)

            # Extraction du code carte (ex: POTD-KR001, POTD-KR020)
            code_match = re.search(r'([A-Z0-9]+-K[R0-9]+)', full_title, re.IGNORECASE)
            if not code_match:
                continue
            card_code = code_match.group(1).upper()

            # Extraction du prix
            price_node = product.select_one('.price .amount, span.price')
            price = 0.0
            if price_node:
                price_match = re.search(r'[\$€]?\s*(\d+[\.,]?\d*)', price_node.get_text())
                if price_match:
                    price = float(price_match.group(1).replace(',', '.'))

            # Détection de la rareté à la fin du titre
            rarity = "Common"
            rarity_patterns = [
                'Quarter Century Secret Rare', 'Prismatic Secret Rare', 'Secret Rare',
                'Ultimate Rare', 'Ultra Rare', 'Super Rare', 'Collector\'s Rare',
                'Ghost Rare', 'Holographic Rare', 'Rare', 'Common'
            ]
            
            for r in rarity_patterns:
                if r.lower() in full_title.lower():
                    rarity = r
                    break

            extracted_data.append({
                'full_title': full_title,
                'card_code': card_code,
                'rarity': rarity,
                'price': price
            })
            items_found += 1

        print(f"  -> {items_found} cartes extraites sur cette page.")

        if items_found == 0:
            break

        # Recherche du bouton page suivante
        next_page = soup.select_one('a.next, a.next-page')
        if not next_page:
            break
        page += 1

    return extracted_data

def update_prices_in_db(set_code, ktcg_url):
    print(f"Scraping des prix pour {set_code} depuis K-TCG...")
    items = scrape_ktcg_all_pages(ktcg_url)
    print(f"\nTotal : {len(items)} déclinaisons récupérées sur K-TCG.")

    if not items:
        return

    conn = get_db_connection()
    c = conn.cursor()
    updated_count = 0

    for item in items:
        query = """
            UPDATE card_rarities r
            SET price = %s
            FROM cards c
            WHERE r.card_id = c.id
            AND c.set_code = %s
            AND c.card_code = %s
            AND LOWER(r.rarity_name) = LOWER(%s)
        """ if DATABASE_URL else """
            UPDATE card_rarities
            SET price = ?
            WHERE card_id IN (
                SELECT id FROM cards WHERE set_code = ? AND card_code = ?
            )
            AND LOWER(rarity_name) = LOWER(?)
        """

        params = (item['price'], set_code, item['card_code'], item['rarity'])
        c.execute(query, params)

        if c.rowcount > 0:
            updated_count += c.rowcount
            print(f" [{item['card_code']}] {item['rarity']} -> ${item['price']}")

    conn.commit()
    conn.close()
    print(f"\nTerminé ! {updated_count} lignes de raretés mises à jour.")

if __name__ == '__main__':
    target_set = "POTD-KR"
    ktcg_url = "https://k-tcg.com/product-category/yugioh/potd-power-of-the-duelist/"
    update_prices_in_db(target_set, ktcg_url)