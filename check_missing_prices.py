from app import get_db_connection

def check_all_sets_prices():
    conn = get_db_connection()
    c = conn.cursor()

    # Récupération de tous les sets enregistrés
    c.execute("SELECT code, name FROM sets ORDER BY code")
    all_sets = c.fetchall()

    if not all_sets:
        print("Aucune extension trouvée en base de données.")
        conn.close()
        return

    print("==================================================")
    print("      RAPPORT DE COUVERTURE DES PRIX DE LA BDD    ")
    print("==================================================\n")

    global_missing = 0

    for set_item in all_sets:
        set_code = set_item[0]
        set_name = set_item[1]

        # Total des raretés pour ce set
        c.execute("""
            SELECT COUNT(*) 
            FROM card_rarities r 
            JOIN cards c ON r.card_id = c.id 
            WHERE c.set_code = %s
        """, (set_code,))
        total = c.fetchone()[0]

        if total == 0:
            print(f"[{set_code}] {set_name} — Aucune carte/rareté enregistrée.")
            print("-" * 50)
            continue

        # Nombre de raretés avec un prix renseigné
        c.execute("""
            SELECT COUNT(*) 
            FROM card_rarities r 
            JOIN cards c ON r.card_id = c.id 
            WHERE c.set_code = %s AND r.price IS NOT NULL AND r.price > 0
        """, (set_code,))
        with_price = c.fetchone()[0]

        # Cartes sans prix
        c.execute("""
            SELECT c.card_code, c.name, r.rarity_name 
            FROM card_rarities r 
            JOIN cards c ON r.card_id = c.id 
            WHERE c.set_code = %s AND (r.price IS NULL OR r.price <= 0)
            ORDER BY c.card_code
        """, (set_code,))
        missing_items = c.fetchall()

        pct = round((with_price / total) * 100, 1)
        missing_count = len(missing_items)
        global_missing += missing_count

        status_flag = "✅" if missing_count == 0 else "⚠️"
        print(f"{status_flag} [{set_code}] {set_name}")
        print(f"   Prix renseignés : {with_price} / {total} ({pct}%)")

        if missing_items:
            print(f"   Manquants ({missing_count}) :")
            for item in missing_items:
                print(f"     - [{item[0]}] {item[1]} ({item[2]})")
        print("-" * 50)

    conn.close()
    print(f"\nAudit terminé. Total global de raretés sans prix : {global_missing}")

if __name__ == '__main__':
    check_all_sets_prices()