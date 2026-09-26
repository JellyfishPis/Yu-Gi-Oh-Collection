import json
import os
from app import get_db_connection, DATABASE_URL

def restore_backup(json_filename):
    if not os.path.exists(json_filename):
        print(f"Fichier {json_filename} introuvable.")
        return

    with open(json_filename, "r", encoding="utf-8") as f:
        backup_data = json.load(f)

    conn = get_db_connection()
    c = conn.cursor()

    restored_count = 0

    for item in backup_data:
        set_code = item["set_code"]
        card_code = item["card_code"]
        rarity_name = item["rarity"]
        qty = item["quantity"]

        # 1. Retrouver l'ID de la rareté correspondante
        query_find = """
            SELECT r.id 
            FROM card_rarities r
            JOIN cards c ON r.card_id = c.id
            WHERE c.set_code = %s AND c.card_code = %s AND r.rarity_name = %s
        """ if DATABASE_URL else """
            SELECT r.id 
            FROM card_rarities r
            JOIN cards c ON r.card_id = c.id
            WHERE c.set_code = ? AND c.card_code = ? AND r.rarity_name = ?
        """
        c.execute(query_find, (set_code, card_code, rarity_name))
        row = c.fetchone()

        if row:
            rarity_id = row[0]
            # 2. Re-placer la quantité
            query_update = "UPDATE card_rarities SET quantity = %s WHERE id = %s" if DATABASE_URL else "UPDATE card_rarities SET quantity = ? WHERE id = ?"
            c.execute(query_update, (qty, rarity_id))
            restored_count += 1
        else:
            print(f"Introuvable dans la BDD : {set_code} - {card_code} ({rarity_name})")

    conn.commit()
    conn.close()
    print(f"\nRestauration terminée : {restored_count} lignes mises à jour.")

if __name__ == '__main__':
    # Indique le nom de ton fichier JSON de sauvegarde ici :
    fichier = input("Nom du fichier JSON à restaurer (ex: backup_collection_20260926_200000.json) : ")
    restore_backup(fichier.strip())