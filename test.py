from app import get_db_connection

conn = get_db_connection()
c = conn.cursor()

# 1. Vérification des codes dans 'cards'
c.execute("SELECT id, card_code, set_code FROM cards WHERE card_code LIKE 'MP24%' OR set_code LIKE 'MP24%' LIMIT 5")
cards_samples = c.fetchall()
print("--- Extrait de la table 'cards' ---")
for row in cards_samples:
    print(f"ID: {row[0]} | card_code: '{row[1]}' | set_code: '{row[2]}'")

# 2. Vérification des liaisons dans 'card_rarities'
if cards_samples:
    sample_id = cards_samples[0][0]
    c.execute("SELECT id, card_id, rarity_name, price FROM card_rarities WHERE card_id = %s", (sample_id,))
    rarities = c.fetchall()
    print(f"\n--- Raretés associées au card_id {sample_id} ---")
    for r in rarities:
        print(f"Rarity ID: {r[0]} | card_id: {r[1]} | rarity_name: '{r[2]}' | price: {r[3]}")

conn.close()