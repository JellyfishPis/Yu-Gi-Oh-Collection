import re
from app import get_db_connection, DATABASE_URL

# Mapping exact d'après la liste Yugipedia OCG-KR
PRICES_BY_NUMBER = {
    1: {'Common': 1.00},
    2: {'Common': 1.00},
    3: {'Common': 1.00},
    4: {'Rare': 1.50},
    5: {'Common': 1.00},
    6: {'Common': 1.00},
    7: {'Ultra Rare': 8.00, 'Ultimate Rare': 45.00},
    8: {'Ultra Rare': 7.00, 'Ultimate Rare': 25.00},
    9: {'Rare': 1.50},
    10: {'Common': 1.00},
    11: {'Common': 1.00},
    12: {'Rare': 1.50},
    13: {'Common': 1.00},
    14: {'Ultra Rare': 6.00, 'Ultimate Rare': 22.00},
    15: {'Rare': 2.00},
    16: {'Rare': 1.50},
    17: {'Rare': 1.50},
    18: {'Rare': 1.50},
    19: {'Rare': 1.50},
    20: {'Rare': 2.50},
    21: {'Super Rare': 3.00, 'Ultimate Rare': 15.00},
    22: {'Super Rare': 3.00, 'Ultimate Rare': 20.00},
    23: {'Super Rare': 3.00, 'Ultimate Rare': 15.00},
    24: {'Rare': 1.50},
    25: {'Common': 1.00},
    26: {'Super Rare': 4.00, 'Ultimate Rare': 25.00},
    27: {'Common': 1.00},
    28: {'Common': 1.00},
    29: {'Common': 1.00},
    30: {'Common': 1.00},
    31: {'Super Rare': 3.00, 'Ultimate Rare': 15.00},
    32: {'Common': 1.00},
    33: {'Ultra Rare': 6.00, 'Ultimate Rare': 20.00},
    34: {'Common': 1.00},
    35: {'Common': 1.00},
    36: {'Common': 1.00},
    37: {'Rare': 1.50},
    38: {'Common': 1.00},
    39: {'Common': 1.00},
    40: {'Common': 1.00},
    41: {'Super Rare': 3.50, 'Ultimate Rare': 18.00},
    42: {'Common': 1.00},
    43: {'Common': 1.00},
    44: {'Common': 1.00},
    45: {'Rare': 2.00},
    46: {'Rare': 1.50},
    47: {'Common': 1.00},
    48: {'Common': 1.00},
    49: {'Common': 1.00},
    50: {'Common': 1.00},
    51: {'Common': 1.00},
    52: {'Common': 1.00},
    53: {'Common': 1.00},
    54: {'Common': 1.00},
    55: {'Super Rare': 3.00, 'Ultimate Rare': 12.00},
    56: {'Common': 1.00},
    57: {'Common': 1.00},
    58: {'Common': 1.00},
    59: {'Common': 1.00},
    60: {'Rare': 1.50}
}

def force_update_fotb():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("SELECT id, card_code FROM cards WHERE set_code LIKE 'FOTB%' ORDER BY card_code ASC")
    cards = c.fetchall()

    updated = 0
    for card_id, card_code in cards:
        match = re.search(r'\d+', card_code)
        if not match:
            continue
        num = int(match.group())

        if num in PRICES_BY_NUMBER:
            for target_rarity, price in PRICES_BY_NUMBER[num].items():
                rarity_root = target_rarity.split()[0]
                pattern = f"%{rarity_root}%"
                
                query = """
                    UPDATE card_rarities 
                    SET price = %s 
                    WHERE card_id = %s 
                    AND (
                        LOWER(rarity_name) LIKE LOWER(%s)
                        OR (%s = 'Common' AND LOWER(rarity_name) IN ('normal', 'short print'))
                    )
                """ if DATABASE_URL else """
                    UPDATE card_rarities 
                    SET price = ? 
                    WHERE card_id = ? 
                    AND (
                        LOWER(rarity_name) LIKE LOWER(?)
                        OR (? = 'Common' AND LOWER(rarity_name) IN ('normal', 'short print'))
                    )
                """
                
                c.execute(query, (price, card_id, pattern, target_rarity))
                if c.rowcount > 0:
                    updated += c.rowcount
                    print(f" [{card_code}] (n°{num}) {target_rarity} -> ${price}")

    conn.commit()
    conn.close()
    print(f"\nMise à jour terminée ! {updated} raretés affectées.")

if __name__ == '__main__':
    force_update_fotb()