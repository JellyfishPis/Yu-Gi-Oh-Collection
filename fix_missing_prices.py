import os
import psycopg2
import sqlite3
from app import get_db_connection, DATABASE_URL

def fix_missing_prices_and_rarities():
    conn = get_db_connection()
    c = conn.cursor()
    is_postgres = bool(DATABASE_URL and "postgresql" in DATABASE_URL)

    # 1. Correction ciblée : uniquement les 4 fausses "Rare" de GAOV-KR
    target_gaov_codes = ('GAOV-KR039', 'GAOV-KR040', 'GAOV-KR065', 'GAOV-KR080')
    
    update_gaov = """
        UPDATE card_rarities
        SET rarity_name = 'Common'
        WHERE rarity_name = 'Rare' AND card_id IN (
            SELECT id FROM cards WHERE card_code IN %s
        )
    """ if is_postgres else """
        UPDATE card_rarities
        SET rarity_name = 'Common'
        WHERE rarity_name = 'Rare' AND card_id IN (
            SELECT id FROM cards WHERE card_code IN (?, ?, ?, ?)
        )
    """
    
    if is_postgres:
        c.execute(update_gaov, (target_gaov_codes,))
    else:
        c.execute(update_gaov, target_gaov_codes)
        
    print(f"Correction ciblée des 'Rare' en 'Common' pour GAOV-KR : {c.rowcount} lignes modifiées.")

    # 2. Récupération stricte des raretés sans prix (les 20 de PAC1, les 2 de LOB, etc.)
    select_missing = """
        SELECT r.id, c.card_code, c.set_code, r.rarity_name
        FROM card_rarities r
        JOIN cards c ON r.card_id = c.id
        WHERE r.price IS NULL OR r.price <= 0
    """
    c.execute(select_missing)
    missing_items = c.fetchall()

    updated_count = 0
    for r_id, card_code, set_code, rarity_name in missing_items:
        approx_price = 0.10  # Valeur plancher par défaut

        # Règles tarifaires approximatives ciblées
        if 'PAC1' in set_code:
            if 'Ultra' in rarity_name:
                approx_price = 1.50
            elif 'Super' in rarity_name:
                approx_price = 1.00
        elif 'GAOV' in set_code:
            if 'Holographic' in rarity_name:
                approx_price = 15.00
            elif 'Common' in rarity_name:
                approx_price = 0.15
        elif 'LOB' in set_code:
            approx_price = 0.20

        update_price = (
            "UPDATE card_rarities SET price = %s WHERE id = %s" 
            if is_postgres else 
            "UPDATE card_rarities SET price = ? WHERE id = ?"
        )
        c.execute(update_price, (approx_price, r_id))
        updated_count += 1
        print(f"[{card_code}] ({rarity_name}) -> Prix attribué : ${approx_price}")

    conn.commit()
    conn.close()
    print(f"\nOpération terminée. {updated_count} prix manquants ont été comblés.")

if __name__ == '__main__':
    fix_missing_prices_and_rarities()