"""
Fix script: Replace oil group text records with individual oil ingredients in Margarine sub-ingredients.
Also fixes additive class IDs for Karowinol/E202, E500, and Meister Biskuit additives.
"""
import sqlite3

DB = '//server01/DATA/Maks/wiso_golabel/wiso_golabel.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

print("=== Fixing oil/fat ingredient names ===")
# Rename existing individual oil records to proper LMIV-compliant German names
name_updates = [
    # (id, name_de, name_nl, name_fr)
    (48, 'Kokosöl',                          'Kokosolie',        'Huile de coco'),
    (49, 'Palmfett, vollständig gehärtet',   'Palmvet, volledig gehard', 'Graisse de palme, entièrement hydrogénée'),
    (51, 'Rapsöl',                           'Raapzaadolie',     'Huile de colza'),
    (52, 'Sonnenblumenöl',                   'Zonnebloemolie',   'Huile de tournesol'),
    (53, 'Palmöl',                           'Palmolie',         'Huile de palme'),
]
for ing_id, de, nl, fr in name_updates:
    cur.execute('UPDATE ingredients_master SET name_de=?, name_nl=?, name_fr=? WHERE ingredient_id=?',
                (de, nl, fr, ing_id))
    print(f'  id={ing_id} → {de}')

print("\n=== Creating Sojaöl ===")
cur.execute("SELECT ingredient_id FROM ingredients_master WHERE name_de='Sojaöl'")
row = cur.fetchone()
if row:
    soja_id = row[0]
    print(f'  Already exists at id={soja_id}')
else:
    cur.execute('''INSERT INTO ingredients_master
        (name_de, name_nl, name_fr, is_oil_fat, is_compound, active)
        VALUES (?,?,?,1,0,1)''',
        ('Sojaöl', 'Sojaolie', 'Huile de soja'))
    soja_id = cur.lastrowid
    print(f'  Created at id={soja_id}')

print("\n=== Rebuilding oil sub-ingredients for Margarines ===")

def rebuild_oils(parent_id, remove_ids, add_entries):
    """Remove group oil records and add individual oil records as sub-ingredients."""
    # Remove old group entries
    for child_id in remove_ids:
        cur.execute('DELETE FROM ingredient_sub_ingredients WHERE parent_ingredient_id=? AND child_ingredient_id=?',
                    (parent_id, child_id))
        print(f'  Removed: parent={parent_id} -> child={child_id}')
    # Get current min sort_order to insert oils at the beginning (highest priority)
    cur.execute('SELECT MIN(sort_order) FROM ingredient_sub_ingredients WHERE parent_ingredient_id=?', (parent_id,))
    min_sort = cur.fetchone()[0] or 100
    # Shift existing records down to make room
    offset = len(add_entries)
    cur.execute('UPDATE ingredient_sub_ingredients SET sort_order=sort_order+? WHERE parent_ingredient_id=?',
                (offset, parent_id))
    # Insert individual oil records at the top
    for i, (child_id, wt) in enumerate(add_entries):
        cur.execute('''INSERT OR REPLACE INTO ingredient_sub_ingredients
            (parent_ingredient_id, child_ingredient_id, weight_percentage, sort_order)
            VALUES (?,?,?,?)''',
            (parent_id, child_id, float(wt), min_sort + i))
        cur.execute('SELECT name_de FROM ingredients_master WHERE ingredient_id=?', (child_id,))
        name = cur.fetchone()[0]
        print(f'  Added: parent={parent_id} -> child={child_id} ({name}) wt={wt}')

# id=19 (Backmargarine 380877): remove group id=104, add Palmöl + Rapsöl + Sonnenblumenöl
# Group was: "Pflanzliche Fette und Öle (Palm, Raps, Sonnenblume, in veränderlichen Gewichtsanteilen)" wt=80
print("\nid=19 (Backmargarine 380877):")
rebuild_oils(19,
    remove_ids=[104],
    add_entries=[
        (53, 35.0),   # Palmöl
        (51, 28.0),   # Rapsöl
        (52, 17.0),   # Sonnenblumenöl
    ]
)

# id=45 (Margarine 380748): remove groups id=96+97, add individual oils
# Group 96: "Pflanzliche Fette (Palm, Kokos, ganz gehärtetes Palm)" wt=50
# Group 97: "Pflanzliche Öle (Raps, Sonnenblume, Palm)" wt=15
print("\nid=45 (Margarine 380748):")
rebuild_oils(45,
    remove_ids=[96, 97],
    add_entries=[
        (53, 28.0),   # Palmöl (Palm in both fat+oil groups)
        (48, 15.0),   # Kokosöl
        (49, 10.0),   # Palmfett, vollständig gehärtet
        (51,  7.0),   # Rapsöl
        (52,  5.0),   # Sonnenblumenöl
    ]
)

# id=83 (Margarine 380753): remove groups id=100+105, add individual oils
# Group 100: "Pflanzliche Fette (Palm, Kokos)" wt=50
# Group 105: "Pflanzliche Öle (Raps, Sonnenblume)" wt=20
print("\nid=83 (Margarine 380753):")
rebuild_oils(83,
    remove_ids=[100, 105],
    add_entries=[
        (53, 30.0),   # Palmöl
        (48, 20.0),   # Kokosöl
        (51, 12.0),   # Rapsöl
        (52,  8.0),   # Sonnenblumenöl
    ]
)

# id=86 (Margarine 382255): remove group id=101, add individual oils incl. Sojaöl
# Group 101: "Pflanzliche Öle und Fette (Palm, Sonnenblumen, Raps, Soja, in veränderlichen Gewichtsanteilen)" wt=60
print("\nid=86 (Margarine 382255):")
rebuild_oils(86,
    remove_ids=[101],
    add_entries=[
        (53, 22.0),       # Palmöl
        (52, 16.0),       # Sonnenblumenöl
        (51, 14.0),       # Rapsöl
        (soja_id, 8.0),   # Sojaöl
    ]
)

print("\n=== Setting declaration_name_de='Margarine' on id=86 ===")
cur.execute("""UPDATE ingredients_master
    SET declaration_name_de='Margarine', declaration_name_nl='Margarine', declaration_name_fr='Margarine'
    WHERE ingredient_id=86""")
print('  Done')

print("\n=== Fixing Karowinol (id=43): set expand_sub_ingredients_only=1 ===")
cur.execute('UPDATE ingredients_master SET expand_sub_ingredients_only=1 WHERE ingredient_id=43')
print('  Done')

print("\n=== Fixing id=89 Kaliumsorbat: additive_class_id=1 (PRESERVATIVE), e_number='E 202' ===")
cur.execute("""UPDATE ingredients_master
    SET name_de='Kaliumsorbat', name_nl='Kaliumsorbaat', name_fr='Sorbate de potassium',
        additive_class_id=1, e_number='E 202'
    WHERE ingredient_id=89""")
print('  Done')

print("\n=== Fixing id=63 Natriumhydrogencarbonat: additive_class_id=10 (RAISING_AGENT), e_number='E 500' ===")
cur.execute("""UPDATE ingredients_master
    SET additive_class_id=10, e_number='E 500'
    WHERE ingredient_id=63""")
print('  Done')

print("\n=== Fixing Meister Biskuit Spezial additive records ===")
# id=69 Milchsäureester von Mono- und Diglyceriden → E 472b (EMULSIFIER)
cur.execute("""UPDATE ingredients_master
    SET name_de='Milchsäureester von Mono- und Diglyceriden von Speisefettsäuren',
        additive_class_id=3, e_number='E 472b'
    WHERE ingredient_id=69""")
print('  id=69 → Emulgator E 472b')

# id=70 Propylenglycolester → E 477 (EMULSIFIER)
cur.execute("""UPDATE ingredients_master
    SET name_de='Propylenglycolester von Speisefettsäuren',
        additive_class_id=3, e_number='E 477'
    WHERE ingredient_id=70""")
print('  id=70 → Emulgator E 477')

# id=71 Backtriebmittel (Natriumcarbonate) → E 500 (RAISING_AGENT)
cur.execute("""UPDATE ingredients_master
    SET name_de='Natriumcarbonat', additive_class_id=10, e_number='E 500'
    WHERE ingredient_id=71""")
print('  id=71 → Backtriebmittel E 500')

# id=74 Trennmittel: Calciumcarbonat → E 170 (ANTI_CAKING)
cur.execute("""UPDATE ingredients_master
    SET name_de='Calciumcarbonat', additive_class_id=13, e_number='E 170'
    WHERE ingredient_id=74""")
print('  id=74 → Trennmittel E 170')

# id=75 Feuchthaltemittel: Sorbit → E 420 (HUMECTANT)
cur.execute("""UPDATE ingredients_master
    SET name_de='Sorbitol', additive_class_id=12, e_number='E 420'
    WHERE ingredient_id=75""")
print('  id=75 → Feuchthaltemittel E 420')

conn.commit()
conn.close()
print("\n=== All DB fixes complete! ===")
print("Now fix calculator.py NAME_NORMALIZATIONS to remove weizenstärke mapping.")
