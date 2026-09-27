import requests
from app import get_db_connection, DATABASE_URL

def update_mp24_prices():
    set_name_api = "25th Anniversary Tin: Dueling Mirrors"
    url = f"https://db.ygoprodeck.com/api/v7/cardinfo.php?cardset={requests.utils.quote(set_name_api)}"
    
    print(f"Interrogation de l'API YGOPRODeck pour '{set_name_api}'...")
    response = requests.get(url)

    if response.status_code != 200:
        print(f"Erreur d'accès à l'API (Code HTTP {response.status_code})")
        return

    data = response.json().get('data', [])
    print(f" -> {len(data)} cartes récupérées depuis l'API.")

    if not data:
        print("Aucune donnée trouvée.")
        return

    # 1. Extraction des prix TCGplayer par numéro de carte (ex: 1 -> 14.33)
    prices_by_number = {}
    for card in data:
        prices = card.get('card_prices', [{}])[0]
        tcg_price = float(prices.get('tcgplayer_price', 0.0))
        
        if tcg_price <= 0:
            continue

        for s in card.get('card_sets', []):
            code_api = s.get('set_code', '').upper()
            if "MP24" in code_api:
                raw_num = ''.join(filter(str.isdigit, code_api))
                if raw_num:
                    prices_by_number[int(raw_num)] = tcg_price

    print(f" -> {len(prices_by_number)} prix valides extraits.")

    conn = get_db_connection()
    c = conn.cursor()

    # 2. Récupération des cartes MP24-FR depuis ta table cards dans Supabase
    c.execute("SELECT id, UPPER(TRIM(card_code)) FROM public.cards WHERE card_code LIKE 'MP24-FR%'")
    db_cards = c.fetchall()
    
    # Dictionnaire de correspondance 'MP24-FR001' -> card_id
    code_to_id = {row[1]: row[0] for row in db_cards}
    print(f" -> {len(code_to_id)} cartes MP24-FR trouvées dans Supabase.")

    updated_count = 0

    # 3. Mise à jour de card_rarities
    for num_int in sorted(prices_by_number.keys()):
        price = prices_by_number[num_int]
        target_code = f"MP24-FR{num_int:03d}"  # Format strict MP24-FR001

        card_id = code_to_id.get(target_code)

        if card_id:
            query = """
                UPDATE public.card_rarities
                SET price = %s
                WHERE card_id = %s
            """ if DATABASE_URL else """
                UPDATE card_rarities
                SET price = ?
                WHERE card_id = ?
            """

            c.execute(query, (price, card_id))

            if c.rowcount > 0:
                updated_count += c.rowcount
                print(f" [{target_code}] (card_id: {card_id}) -> ${price}")

    conn.commit()
    conn.close()
    print(f"\nTerminé ! {updated_count} prix de cartes MP24-FR mis à jour dans Supabase.")

if __name__ == '__main__':
    update_mp24_prices()