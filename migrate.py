import os
import sqlite3
import psycopg2

# URL de ton Supabase (mets ta vraie URL ici ou via variable d'environnement)
SUPABASE_URL = "postgresql://postgres.eplaexjlmipvedfhwimk:2uMkgSfzLP.BAsq@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"

def migrate():
    if not os.path.exists("database.db"):
        print("Erreur : Aucun fichier database.db trouvé en local.")
        return

    # Connexion SQLite local
    sqlite_conn = sqlite3.connect("database.db")
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # Connexion Supabase PostgreSQL
    pg_conn = psycopg2.connect(SUPABASE_URL, sslmode='require')
    pg_cursor = pg_conn.cursor()

    print("Début de la migration vers Supabase...")

    # 1. Copier les sets
    sqlite_cursor.execute("SELECT code, name, url FROM sets")
    sets = sqlite_cursor.fetchall()
    for s in sets:
        pg_cursor.execute("""
            INSERT INTO sets (code, name, url) VALUES (%s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, url = EXCLUDED.url
        """, (s['code'], s['name'], s['url']))
    print(f"-> {len(sets)} sets copiés.")

    # 2. Copier les cartes
    sqlite_cursor.execute("SELECT id, set_code, card_code, name, image_url FROM cards")
    cards = sqlite_cursor.fetchall()
    for card in cards:
        pg_cursor.execute("""
            INSERT INTO cards (id, set_code, card_code, name, image_url) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (card['id'], card['set_code'], card['card_code'], card['name'], card['image_url']))
    print(f"-> {len(cards)} cartes copiées.")

    # 3. Copier les raretés et quantités
    sqlite_cursor.execute("SELECT id, card_id, rarity_name, quantity FROM card_rarities")
    rarities = sqlite_cursor.fetchall()
    for r in rarities:
        pg_cursor.execute("""
            INSERT INTO card_rarities (id, card_id, rarity_name, quantity) VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET quantity = EXCLUDED.quantity
        """, (r['id'], r['card_id'], r['rarity_name'], r['quantity']))
    print(f"-> {len(rarities)} raretés/quantités copiées.")

    pg_conn.commit()
    sqlite_conn.close()
    pg_conn.close()
    print("Migration terminée avec succès !")

if __name__ == '__main__':
    migrate()