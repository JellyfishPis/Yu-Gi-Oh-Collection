import json
from datetime import datetime
from app import get_db_connection

def create_backup():
    conn = get_db_connection()
    c = conn.cursor()

    # Récupère uniquement les cartes que tu possèdes (quantité > 0)
    query = """
        SELECT s.code AS set_code, c.card_code, c.name, r.rarity_name, r.quantity
        FROM card_rarities r
        JOIN cards c ON r.card_id = c.id
        JOIN sets s ON c.set_code = s.code
        WHERE r.quantity > 0
        ORDER BY s.code, c.card_code
    """
    c.execute(query)
    rows = c.fetchall()

    backup_data = []
    for row in rows:
        backup_data.append({
            "set_code": row[0],
            "card_code": row[1],
            "card_name": row[2],
            "rarity": row[3],
            "quantity": row[4]
        })

    conn.close()

    filename = f"backup_collection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=4, ensure_ascii=False)

    print(f" Backup réussi ! Fichier créé : {filename} ({len(backup_data)} entrées)")

if __name__ == '__main__':
    create_backup()