#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for Zutaten V2

Fills database with test ingredients and creates
example recipe composition with label generation.

Usage:
    python -m backend.zutaten_v2.test_data --db-path wiso_golabel.db
"""

import sqlite3
import json
import argparse
import sys
import io
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Import generator
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.zutaten_v2.enums import Language
from backend.zutaten_v2.database import ZutatenDatabase
from backend.zutaten_v2.generator import generate_label, generate_all_languages


def get_connection(db_path: str) -> sqlite3.Connection:
    """Get database connection"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_allergen_id(conn: sqlite3.Connection, code: str) -> int:
    """Get allergen ID by code"""
    cursor = conn.cursor()
    cursor.execute("SELECT allergen_id FROM allergens_reference WHERE allergen_code = ?", (code,))
    row = cursor.fetchone()
    return row['allergen_id'] if row else None


def get_additive_class_id(conn: sqlite3.Connection, code: str) -> int:
    """Get additive class ID by code"""
    cursor = conn.cursor()
    cursor.execute("SELECT class_id FROM additive_classes WHERE class_code = ?", (code,))
    row = cursor.fetchone()
    return row['class_id'] if row else None


def insert_ingredient(conn: sqlite3.Connection, data: dict) -> int:
    """Insert ingredient and return its ID"""
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Check if already exists
    cursor.execute(
        "SELECT ingredient_id FROM ingredients_master WHERE ingredient_code = ?",
        (data['ingredient_code'],)
    )
    existing = cursor.fetchone()
    if existing:
        print(f"  [SKIP] {data['ingredient_code']} already exists")
        return existing['ingredient_id']

    cursor.execute('''
        INSERT INTO ingredients_master (
            ingredient_code, name_de, name_nl, name_fr, category,
            allergen_id, additive_class_id, e_number,
            is_compound, is_added_water, is_nano, is_oil_fat,
            botanical_origin_de, botanical_origin_nl, botanical_origin_fr,
            active, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
    ''', (
        data['ingredient_code'],
        data.get('name_de', ''),
        data.get('name_nl', ''),
        data.get('name_fr', ''),
        data.get('category', ''),
        data.get('allergen_id'),
        data.get('additive_class_id'),
        data.get('e_number'),
        data.get('is_compound', False),
        data.get('is_added_water', False),
        data.get('is_nano', False),
        data.get('is_oil_fat', False),
        data.get('botanical_origin_de'),
        data.get('botanical_origin_nl'),
        data.get('botanical_origin_fr'),
        now, now
    ))

    ingredient_id = cursor.lastrowid
    print(f"  [OK] {data['ingredient_code']} -> ID {ingredient_id}")
    return ingredient_id


def create_test_ingredients(db_path: str):
    """Create test ingredients for bakery"""
    print("\n" + "="*60)
    print("CREATING TEST INGREDIENTS")
    print("="*60)

    conn = get_connection(db_path)

    # Get allergen IDs
    gluten_id = get_allergen_id(conn, 'GLUTEN')
    eggs_id = get_allergen_id(conn, 'EGGS')
    milk_id = get_allergen_id(conn, 'MILK')
    nuts_id = get_allergen_id(conn, 'NUTS')
    soy_id = get_allergen_id(conn, 'SOYBEANS')

    # Get additive class IDs
    preservative_id = get_additive_class_id(conn, 'PRESERVATIVE')
    emulsifier_id = get_additive_class_id(conn, 'EMULSIFIER')
    raising_agent_id = get_additive_class_id(conn, 'RAISING_AGENT')
    antioxidant_id = get_additive_class_id(conn, 'ANTIOXIDANT')

    # Test ingredients list for "Black Forest" cake
    test_ingredients = [
        # Flour
        {
            'ingredient_code': 'WEIZENMEHL_T405',
            'name_de': 'Weizenmehl Type 405',
            'name_nl': 'Tarwebloem Type 405',
            'name_fr': 'Farine de blé Type 405',
            'category': 'flour',
            'allergen_id': gluten_id
        },
        # Sugar
        {
            'ingredient_code': 'ZUCKER_WEISS',
            'name_de': 'Zucker',
            'name_nl': 'Suiker',
            'name_fr': 'Sucre',
            'category': 'sugar'
        },
        # Eggs
        {
            'ingredient_code': 'VOLLEI_FRISCH',
            'name_de': 'Vollei',
            'name_nl': 'Heel ei',
            'name_fr': 'Oeuf entier',
            'category': 'egg',
            'allergen_id': eggs_id
        },
        # Butter
        {
            'ingredient_code': 'BUTTER_SUESS',
            'name_de': 'Butter',
            'name_nl': 'Boter',
            'name_fr': 'Beurre',
            'category': 'dairy',
            'allergen_id': milk_id
        },
        # Cream
        {
            'ingredient_code': 'SAHNE_30',
            'name_de': 'Sahne (30% Fett)',
            'name_nl': 'Slagroom (30% vet)',
            'name_fr': 'Creme (30% MG)',
            'category': 'dairy',
            'allergen_id': milk_id
        },
        # Cocoa
        {
            'ingredient_code': 'KAKAOPULVER',
            'name_de': 'Kakaopulver',
            'name_nl': 'Cacaopoeder',
            'name_fr': 'Poudre de cacao',
            'category': 'chocolate'
        },
        # Chocolate (compound ingredient)
        {
            'ingredient_code': 'ZARTBITTER_SCHOKO',
            'name_de': 'Zartbitterschokolade',
            'name_nl': 'Pure chocolade',
            'name_fr': 'Chocolat noir',
            'category': 'chocolate',
            'is_compound': True,
            'allergen_id': soy_id  # Soy lecithin in chocolate
        },
        # Cherries
        {
            'ingredient_code': 'SAUERKIRSCHEN',
            'name_de': 'Sauerkirschen',
            'name_nl': 'Zure kersen',
            'name_fr': 'Cerises griottes',
            'category': 'fruit'
        },
        # Kirsch (cherry brandy)
        {
            'ingredient_code': 'KIRSCHWASSER',
            'name_de': 'Kirschwasser',
            'name_nl': 'Kirsch',
            'name_fr': 'Kirsch',
            'category': 'flavoring'
        },
        # Vanilla extract
        {
            'ingredient_code': 'VANILLE_EXTRAKT',
            'name_de': 'Vanilleextrakt',
            'name_nl': 'Vanille-extract',
            'name_fr': 'Extrait de vanille',
            'category': 'flavoring'
        },
        # Raising agent (additive)
        {
            'ingredient_code': 'BACKPULVER',
            'name_de': 'Backtriebmittel',
            'name_nl': 'Rijsmiddel',
            'name_fr': 'Poudre a lever',
            'category': 'other',
            'additive_class_id': raising_agent_id,
            'e_number': 'E 500'
        },
        # Emulsifier (soy lecithin)
        {
            'ingredient_code': 'SOJALECITHIN',
            'name_de': 'Sojalecithin',
            'name_nl': 'Sojalecithine',
            'name_fr': 'Lecithine de soja',
            'category': 'other',
            'additive_class_id': emulsifier_id,
            'e_number': 'E 322',
            'allergen_id': soy_id
        },
        # Water
        {
            'ingredient_code': 'WASSER',
            'name_de': 'Wasser',
            'name_nl': 'Water',
            'name_fr': 'Eau',
            'category': 'other',
            'is_added_water': True
        },
        # Gelatin
        {
            'ingredient_code': 'GELATINE',
            'name_de': 'Gelatine',
            'name_nl': 'Gelatine',
            'name_fr': 'Gelatine',
            'category': 'other'
        },
        # Almonds (for decoration)
        {
            'ingredient_code': 'MANDELN_GEHOBELT',
            'name_de': 'Mandelblaettchen',
            'name_nl': 'Amandelschaafsel',
            'name_fr': 'Amandes effilees',
            'category': 'nut',
            'allergen_id': nuts_id
        },
    ]

    ingredient_ids = {}

    for ing_data in test_ingredients:
        ingredient_id = insert_ingredient(conn, ing_data)
        ingredient_ids[ing_data['ingredient_code']] = ingredient_id

    conn.commit()
    conn.close()

    print(f"\n[OK] Created/found {len(ingredient_ids)} ingredients")
    return ingredient_ids


def find_or_create_test_recipe(db_path: str) -> str:
    """Find existing recipe or create test one"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Try to find existing recipe
    cursor.execute("SELECT article_nr, name FROM recipes LIMIT 1")
    row = cursor.fetchone()

    if row:
        article_nr = row['article_nr']
        print(f"\n[INFO] Using existing recipe: {article_nr} - {row['name']}")
        conn.close()
        return article_nr

    # If no recipes - create test one
    article_nr = "TEST001"
    cursor.execute('''
        INSERT OR IGNORE INTO recipes (article_nr, name, category, active)
        VALUES (?, ?, ?, 1)
    ''', (article_nr, "Schwarzwaelder Kirschtorte (Test)", "Torten"))

    conn.commit()
    conn.close()

    print(f"\n[INFO] Created test recipe: {article_nr}")
    return article_nr


def create_recipe_composition(db_path: str, article_nr: str, ingredient_ids: dict):
    """Create recipe composition (Black Forest Cake)"""
    print("\n" + "="*60)
    print(f"CREATING RECIPE COMPOSITION: {article_nr}")
    print("="*60)

    conn = get_connection(db_path)
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    # Delete old composition (if exists)
    cursor.execute("DELETE FROM recipe_ingredients WHERE article_nr = ?", (article_nr,))

    # Black Forest Cake composition (per 1000g final product)
    # Sorted by weight (descending) - as required by LMIV Art. 18
    composition = [
        # Ingredient, Weight (g), QUID (show %)
        ('SAHNE_30', 250, True),           # Cream - main ingredient
        ('WEIZENMEHL_T405', 180, False),   # Flour
        ('ZUCKER_WEISS', 150, False),      # Sugar
        ('SAUERKIRSCHEN', 120, True),      # Cherries - highlighted
        ('VOLLEI_FRISCH', 100, False),     # Eggs
        ('ZARTBITTER_SCHOKO', 80, False),  # Chocolate
        ('BUTTER_SUESS', 60, False),       # Butter
        ('WASSER', 50, False),             # Water
        ('KAKAOPULVER', 30, False),        # Cocoa
        ('KIRSCHWASSER', 20, False),       # Kirsch
        ('GELATINE', 15, False),           # Gelatin
        ('VANILLE_EXTRAKT', 5, False),     # Vanilla
        ('BACKPULVER', 5, False),          # Raising agent
        ('SOJALECITHIN', 3, False),        # Emulsifier
        ('MANDELN_GEHOBELT', 10, False),   # Almonds (decoration)
    ]

    for code, weight, highlight_quid in composition:
        if code not in ingredient_ids:
            print(f"  [SKIP] Ingredient {code} not found")
            continue

        cursor.execute('''
            INSERT INTO recipe_ingredients (article_nr, ingredient_id, weight_grams, highlight_quid, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (article_nr, ingredient_ids[code], weight, highlight_quid, now, now))

        print(f"  [OK] {code}: {weight}г" + (" (QUID)" if highlight_quid else ""))

    conn.commit()
    conn.close()

    print(f"\n[OK] Recipe composition created ({len(composition)} ingredients)")


def generate_test_labels(db_path: str, article_nr: str):
    """Generate test labels in all languages"""
    print("\n" + "="*60)
    print("GENERATING LABELS (LMIV)")
    print("="*60)

    db = ZutatenDatabase(db_path)

    # Get recipe data
    recipe = db.get_recipe_for_label(
        article_nr=article_nr,
        final_weight=1000  # Final product (after baking)
    )

    if not recipe:
        print("[ERROR] Recipe not found or no ingredients!")
        return

    print(f"\nRecipe: {recipe.article_nr}")
    print(f"Input weight: {recipe.total_input_weight}g")
    print(f"Final product: {recipe.final_product_weight}g")
    print(f"Ingredients: {len(recipe.ingredients)}")

    # Generate labels in all languages
    for lang in [Language.DE, Language.NL, Language.FR]:
        print(f"\n{'─'*60}")
        print(f"🌍 {lang.value.upper()} - {lang.name}")
        print('─'*60)

        label = generate_label(recipe, lang)

        # Print label text
        print(f"\n{label.label_text}")

        # Print allergens
        if label.allergens_present:
            print(f"\nAllergens: {', '.join(label.allergens_present)}")

    print("\n" + "="*60)
    print("[OK] LABELS GENERATED SUCCESSFULLY")
    print("="*60)


def run_full_test(db_path: str):
    """Run full test"""
    print("\n" + "="*60)
    print("ZUTATEN V2 - FULL TEST")
    print("="*60)
    print(f"Database: {db_path}")

    # 1. Create ingredients
    ingredient_ids = create_test_ingredients(db_path)

    # 2. Find or create recipe
    article_nr = find_or_create_test_recipe(db_path)

    # 3. Create recipe composition
    create_recipe_composition(db_path, article_nr, ingredient_ids)

    # 4. Generate labels
    generate_test_labels(db_path, article_nr)

    print("\n" + "="*60)
    print("[OK] TEST COMPLETED SUCCESSFULLY!")
    print("="*60)
    print(f"\nYou can now:")
    print(f"1. Open Admin UI -> tab 'Zutaten'")
    print(f"2. View ingredients in 'Base ingredients'")
    print(f"3. Select recipe {article_nr} in 'Recipe composition'")
    print(f"4. Generate label in 'Label generation'")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Zutaten V2 Test Data')
    parser.add_argument('--db-path', type=str, default='wiso_golabel.db',
                        help='Path to SQLite database')

    args = parser.parse_args()

    # Check if database exists
    if not Path(args.db_path).exists():
        print(f"[ERROR] Database not found: {args.db_path}")
        print("Specify correct path via --db-path")
        exit(1)

    run_full_test(args.db_path)
