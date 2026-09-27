import re
import time
import cloudscraper
from bs4 import BeautifulSoup
from app import get_db_connection, DATABASE_URL

# Scraper simulant un vrai navigateur pour éviter l'erreur 403
SCRAPER = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

def find_ktcg_set_url(set_code):
    prefix = set_code.split('-')[0].lower()
    category_base_url = "https://k-tcg.com/product-category/yugioh/"
    
    print(f"Recherche automatique de l'URL K-TCG pour le préfixe '{prefix.upper()}'...")
    response = SCRAPER.get(category_base_url)
    if response.status_code != 200:
        print(f"Erreur d'accès à la catégorie (Statut HTTP {response.status_code})")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/product-category/yugioh/' in href and f"/{prefix}-" in href.lower():
            print(f"URL trouvée : {href}")
            return href

    return None

def scrape_ktcg_all_pages(base_url):
    extracted_data = []
    page = 1

    # Dictionnaire de correspondance pour normaliser les raretés K-TCG
    rarity_map = {
        'Prismatic': 'Prismatic Secret Rare',
        'Secret': 'Secret Rare',
        'Parallel': 'Parallel Rare',
        'Ultra': 'Ultra Rare',
        'Super': 'Super Rare',
        'Ultimate': 'Ultimate Rare',
        'Collector\'s': 'Collector\'s Rare',
        'Extra Secret': 'Extra Secret Rare'
    }

    # Liste des motifs de rareté ordonnée par précision
    rarity_patterns = [
        'Quarter Century Secret Rare', 'Prismatic Secret Rare', 'Extra Secret Rare',
        'Gold Secret Rare', 'Premium Gold Rare', 'Secret Rare', 'Collector\'s Rare', 
        'Ultimate Rare', 'Ultra Rare', 'Super Rare', 'Rare', 'Prismatic', 'Secret', 'Parallel', 'Common'
    ]

    while True:
        page_url = f"{base_url.rstrip('/')}/page/{page}/" if page > 1 else base_url
        print(f"Scraping page {page} : {page_url}")
        
        response = SCRAPER.get(page_url)
        if response.status_code != 200:
            print(f"  -> Fin des pages (statut HTTP {response.status_code}).")
            break

        soup = BeautifulSoup(response.text, 'html.parser')
        
        products = soup.select('ul.products li.product, div.products div.product')
        if not products:
            products = soup.find_all(['li', 'div'], class_=re.compile(r'\bproduct\b'))

        if not products:
            print("  -> Aucun produit sur cette page. Fin du scraping.")
            break

        items_found = 0
        for product in products:
            title_node = product.select_one('.woocommerce-loop-product__title, .product-title, h2, h3')
            if not title_node:
                continue

            full_title = title_node.get_text(strip=True)

            # Extraction du code carte (ex: PAC1-KR001, PAC1-K001)
            code_match = re.search(r'([A-Z0-9]+-K[R]?[0-9]+)', full_title, re.IGNORECASE)
            if not code_match:
                continue
            card_code = code_match.group(1).upper()

            # Extraction du prix (priorité à la réduction <ins> s'il y en a une)
            price = 0.0
            price_ins = product.select_one('.price ins .amount, ins span.amount')
            price_node = price_ins if price_ins else product.select_one('.price .amount, span.price')

            if price_node:
                price_match = re.search(r'[\$€]?\s*(\d+[\.,]?\d*)', price_node.get_text())
                if price_match:
                    price = float(price_match.group(1).replace(',', '.'))

            # Extraction de la rareté
            raw_rarity = "Common"
            for r in rarity_patterns:
                if r.lower() in full_title.lower():
                    raw_rarity = r
                    break

            # Conversion vers le nom standardisé
            final_rarity = rarity_map.get(raw_rarity, raw_rarity)

            extracted_data.append({
                'full_title': full_title,
                'card_code': card_code,
                'rarity': final_rarity,
                'price': price
            })
            items_found += 1

        print(f"  -> {items_found} cartes extraites.")

        if items_found == 0:
            break

        page += 1
        time.sleep(0.25)

    return extracted_data

def update_prices_in_db(set_code):
    ktcg_url = find_ktcg_set_url(set_code)
    if not ktcg_url:
        return

    items = scrape_ktcg_all_pages(ktcg_url)
    print(f"\nTotal : {len(items)} déclinaisons récupérées sur K-TCG.")

    if not items:
        return

    conn = get_db_connection()
    c = conn.cursor()
    updated_count = 0

    for item in items:
        # On extrait le mot racine de la rareté (ex: 'Secret' pour 'Secret Rare' ou 'Secret')
        rarity_root = item['rarity'].split()[0]
        rarity_pattern = f"%{rarity_root}%"

        query = """
            UPDATE card_rarities r
            SET price = %s
            FROM cards c
            WHERE r.card_id = c.id
            AND c.set_code = %s
            AND c.card_code = %s
            AND LOWER(r.rarity_name) LIKE LOWER(%s)
        """ if DATABASE_URL else """
            UPDATE card_rarities
            SET price = ?
            WHERE card_id IN (
                SELECT id FROM cards WHERE set_code = ? AND card_code = ?
            )
            AND LOWER(rarity_name) LIKE LOWER(?)
        """

        if DATABASE_URL:
            c.execute(query, (item['price'], set_code, item['card_code'], rarity_pattern))
        else:
            c.execute(query, (item['price'], set_code, item['card_code'], rarity_pattern))

        if c.rowcount > 0:
            updated_count += c.rowcount
            print(f" [{item['card_code']}] {item['rarity']} -> ${item['price']}")

    conn.commit()
    conn.close()
    print(f"\nTerminé ! {updated_count} lignes de raretés mises à jour.")

if __name__ == '__main__':
    target_set = "LOB-K"
    update_prices_in_db(target_set)