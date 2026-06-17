#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZUTATEN ADMIN UI - Ð£Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð°Ð¼Ð¸ (LMIV)
Tkinter Ð¸Ð½Ñ‚ÐµÑ€Ñ„ÐµÐ¹Ñ Ð´Ð»Ñ Ñ€Ð°Ð±Ð¾Ñ‚Ñ‹ Ñ ÑÐ¸ÑÑ‚ÐµÐ¼Ð¾Ð¹ Zutaten V2

Ð¤ÑƒÐ½ÐºÑ†Ð¸Ð¸:
- ÐŸÑ€Ð¾ÑÐ¼Ð¾Ñ‚Ñ€ Ð¸ Ð¿Ð¾Ð¸ÑÐº Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð²
- Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¸Ðµ/Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð² (DE/NL/FR)
- Ð£Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐ¾ÑÑ‚Ð°Ð²Ð¾Ð¼ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð²
- Ð“ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ñ Ð¸ Ð¿Ñ€ÐµÐ´Ð¿Ñ€Ð¾ÑÐ¼Ð¾Ñ‚Ñ€ ÑÑ‚Ð¸ÐºÐµÑ‚Ð¾Ðº Ð½Ð° 3 ÑÐ·Ñ‹ÐºÐ°Ñ…
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import asyncio
import websockets
import json
import threading
from datetime import datetime

# ============================================
# ÐÐÐ¡Ð¢Ð ÐžÐ™ÐšÐ˜
# ============================================
SERVER_URL = "ws://server01:8080/ws/admin"

# ============================================
# Ð“Ð›ÐÐ’ÐÐžÐ• ÐžÐšÐÐž
# ============================================
class ZutatenAdminPanel(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("ðŸ¥„ ZUTATEN ADMIN - Ð£Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð°Ð¼Ð¸ (LMIV)")
        self.geometry("1400x800")

        # Ð”Ð°Ð½Ð½Ñ‹Ðµ
        self.ingredients = []
        self.allergens = []
        self.additive_classes = []
        self.current_ingredient = None
        self.ws = None
        self.ws_loop = None

        self.create_widgets()

        # Ð—Ð°Ð¿ÑƒÑÐºÐ°ÐµÐ¼ WebSocket Ð² Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ
        self.ws_thread = threading.Thread(target=self.run_websocket, daemon=True)
        self.ws_thread.start()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        """Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¸Ðµ Ð¸Ð½Ñ‚ÐµÑ€Ñ„ÐµÐ¹ÑÐ°"""
        # Ð—Ð°Ð³Ð¾Ð»Ð¾Ð²Ð¾Ðº
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(header, text="ðŸ¥„ Ð£ÐŸÐ ÐÐ’Ð›Ð•ÐÐ˜Ð• Ð˜ÐÐ“Ð Ð•Ð”Ð˜Ð•ÐÐ¢ÐÐœÐ˜ (LMIV)",
                  font=("Arial", 16, "bold")).pack(side=tk.LEFT)

        self.status_label = ttk.Label(header, text="âšª ÐžÑ‚ÐºÐ»ÑŽÑ‡ÐµÐ½", font=("Arial", 11))
        self.status_label.pack(side=tk.RIGHT)

        # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ notebook (Ð²ÐºÐ»Ð°Ð´ÐºÐ¸)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Ð’ÐºÐ»Ð°Ð´ÐºÐ° 1: Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð²
        self.create_ingredients_tab()

        # Ð’ÐºÐ»Ð°Ð´ÐºÐ° 2: Ð ÐµÐ´Ð°ÐºÑ‚Ð¾Ñ€ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð°
        self.create_editor_tab()

        # Ð’ÐºÐ»Ð°Ð´ÐºÐ° 3: Ð¡Ð¾ÑÑ‚Ð°Ð² Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°
        self.create_recipe_tab()

        # Ð’ÐºÐ»Ð°Ð´ÐºÐ° 4: Ð“ÐµÐ½ÐµÑ€Ð°Ñ‚Ð¾Ñ€ ÑÑ‚Ð¸ÐºÐµÑ‚Ð¾Ðº
        self.create_label_tab()

    # ============================================
    # Ð’ÐšÐ›ÐÐ”ÐšÐ 1: Ð¡ÐŸÐ˜Ð¡ÐžÐš Ð˜ÐÐ“Ð Ð•Ð”Ð˜Ð•ÐÐ¢ÐžÐ’
    # ============================================
    def create_ingredients_tab(self):
        """Ð’ÐºÐ»Ð°Ð´ÐºÐ° ÑÐ¾ ÑÐ¿Ð¸ÑÐºÐ¾Ð¼ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð²"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="ðŸ“‹ Ð˜Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ñ‹")

        # ÐŸÐ°Ð½ÐµÐ»ÑŒ Ð¿Ð¾Ð¸ÑÐºÐ°
        search_frame = ttk.Frame(tab)
        search_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(search_frame, text="ÐŸÐ¾Ð¸ÑÐº:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace('w', lambda *args: self.filter_ingredients())
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT, padx=5)

        ttk.Label(search_frame, text="ÐšÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ:").pack(side=tk.LEFT, padx=5)
        self.category_var = tk.StringVar(value="Ð’ÑÐµ")
        self.category_combo = ttk.Combobox(search_frame, textvariable=self.category_var,
                                           values=["Ð’ÑÐµ", "flour", "sugar", "dairy", "egg", "fat",
                                                   "nut", "fruit", "chocolate", "additive", "other"],
                                           width=15)
        self.category_combo.pack(side=tk.LEFT, padx=5)
        self.category_combo.bind('<<ComboboxSelected>>', lambda e: self.filter_ingredients())

        ttk.Button(search_frame, text="ðŸ”„ ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ",
                   command=self.refresh_ingredients).pack(side=tk.LEFT, padx=10)
        ttk.Button(search_frame, text="âž• ÐÐ¾Ð²Ñ‹Ð¹ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚",
                   command=self.new_ingredient).pack(side=tk.LEFT, padx=5)

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð²
        columns = ('code', 'name_de', 'name_nl', 'name_fr', 'category', 'allergen', 'additive')
        self.ingredients_tree = ttk.Treeview(tab, columns=columns, show='headings', height=20)

        self.ingredients_tree.heading('code', text='ÐšÐ¾Ð´')
        self.ingredients_tree.heading('name_de', text='DE (Deutsch)')
        self.ingredients_tree.heading('name_nl', text='NL (Nederlands)')
        self.ingredients_tree.heading('name_fr', text='FR (FranÃ§ais)')
        self.ingredients_tree.heading('category', text='ÐšÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ')
        self.ingredients_tree.heading('allergen', text='ÐÐ»Ð»ÐµÑ€Ð³ÐµÐ½')
        self.ingredients_tree.heading('additive', text='Ð”Ð¾Ð±Ð°Ð²ÐºÐ°')

        self.ingredients_tree.column('code', width=120)
        self.ingredients_tree.column('name_de', width=180)
        self.ingredients_tree.column('name_nl', width=180)
        self.ingredients_tree.column('name_fr', width=180)
        self.ingredients_tree.column('category', width=100)
        self.ingredients_tree.column('allergen', width=120)
        self.ingredients_tree.column('additive', width=150)

        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.ingredients_tree.yview)
        self.ingredients_tree.configure(yscroll=scrollbar.set)

        self.ingredients_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        # Ð¦Ð²ÐµÑ‚Ð¾Ð²Ñ‹Ðµ Ñ‚ÐµÐ³Ð¸
        self.ingredients_tree.tag_configure('allergen', background='#FFECB3')
        self.ingredients_tree.tag_configure('additive', background='#E1BEE7')

        # Ð”Ð²Ð¾Ð¹Ð½Ð¾Ð¹ ÐºÐ»Ð¸Ðº Ð´Ð»Ñ Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ
        self.ingredients_tree.bind('<Double-1>', self.edit_selected_ingredient)

    # ============================================
    # Ð’ÐšÐ›ÐÐ”ÐšÐ 2: Ð Ð•Ð”ÐÐšÐ¢ÐžÐ  Ð˜ÐÐ“Ð Ð•Ð”Ð˜Ð•ÐÐ¢Ð
    # ============================================
    def create_editor_tab(self):
        """Ð’ÐºÐ»Ð°Ð´ÐºÐ° Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¾Ñ€Ð° Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð°"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="âœï¸ Ð ÐµÐ´Ð°ÐºÑ‚Ð¾Ñ€")

        # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ frame Ñ Ð¿Ñ€Ð¾ÐºÑ€ÑƒÑ‚ÐºÐ¾Ð¹
        canvas = tk.Canvas(tab)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # ÐžÑÐ½Ð¾Ð²Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ
        basic_frame = ttk.LabelFrame(scrollable_frame, text="ðŸ“ ÐžÑÐ½Ð¾Ð²Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ")
        basic_frame.pack(fill=tk.X, padx=10, pady=5)

        # ÐšÐ¾Ð´
        row = ttk.Frame(basic_frame)
        row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row, text="ÐšÐ¾Ð´:", width=20).pack(side=tk.LEFT)
        self.code_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.code_var, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Label(row, text="(Ð½Ð°Ð¿Ñ€. FLOUR_WHEAT, SUGAR_WHITE)",
                  foreground="gray").pack(side=tk.LEFT)

        # ÐÐ°Ð·Ð²Ð°Ð½Ð¸Ñ
        names_frame = ttk.LabelFrame(scrollable_frame, text="ðŸŒ ÐÐ°Ð·Ð²Ð°Ð½Ð¸Ñ (Ð¼ÑƒÐ»ÑŒÑ‚Ð¸ÑÐ·Ñ‹Ñ‡Ð½Ð¾ÑÑ‚ÑŒ)")
        names_frame.pack(fill=tk.X, padx=10, pady=5)

        for lang, label in [('de', 'Deutsch (DE) *'), ('nl', 'Nederlands (NL)'), ('fr', 'FranÃ§ais (FR)')]:
            row = ttk.Frame(names_frame)
            row.pack(fill=tk.X, padx=5, pady=2)
            ttk.Label(row, text=f"{label}:", width=20).pack(side=tk.LEFT)
            var = tk.StringVar()
            setattr(self, f'name_{lang}_var', var)
            ttk.Entry(row, textvariable=var, width=40).pack(side=tk.LEFT, padx=5)

        # ÐšÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ
        cat_frame = ttk.Frame(scrollable_frame)
        cat_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(cat_frame, text="ÐšÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ:", width=20).pack(side=tk.LEFT)
        self.edit_category_var = tk.StringVar()
        ttk.Combobox(cat_frame, textvariable=self.edit_category_var,
                     values=["flour", "sugar", "dairy", "egg", "fat", "nut",
                             "fruit", "chocolate", "flavoring", "additive", "other"],
                     width=20).pack(side=tk.LEFT, padx=5)

        # ÐÐ»Ð»ÐµÑ€Ð³ÐµÐ½
        allergen_frame = ttk.LabelFrame(scrollable_frame, text="âš ï¸ ÐÐ»Ð»ÐµÑ€Ð³ÐµÐ½ (Art. 21 LMIV)")
        allergen_frame.pack(fill=tk.X, padx=10, pady=5)

        row = ttk.Frame(allergen_frame)
        row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row, text="ÐÐ»Ð»ÐµÑ€Ð³ÐµÐ½:", width=20).pack(side=tk.LEFT)
        self.allergen_var = tk.StringVar(value="ÐÐµÑ‚")
        self.allergen_combo = ttk.Combobox(row, textvariable=self.allergen_var, width=40)
        self.allergen_combo.pack(side=tk.LEFT, padx=5)

        # Ð”Ð¾Ð±Ð°Ð²ÐºÐ¸
        additive_frame = ttk.LabelFrame(scrollable_frame, text="ðŸ§ª ÐŸÐ¸Ñ‰ÐµÐ²Ð°Ñ Ð´Ð¾Ð±Ð°Ð²ÐºÐ° (Annex VII Part C)")
        additive_frame.pack(fill=tk.X, padx=10, pady=5)

        row = ttk.Frame(additive_frame)
        row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row, text="ÐšÐ»Ð°ÑÑ Ð´Ð¾Ð±Ð°Ð²ÐºÐ¸:", width=20).pack(side=tk.LEFT)
        self.additive_class_var = tk.StringVar(value="ÐÐµÑ‚")
        self.additive_combo = ttk.Combobox(row, textvariable=self.additive_class_var, width=40)
        self.additive_combo.pack(side=tk.LEFT, padx=5)

        row = ttk.Frame(additive_frame)
        row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(row, text="E-Ð½Ð¾Ð¼ÐµÑ€:", width=20).pack(side=tk.LEFT)
        self.e_number_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.e_number_var, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Label(row, text="(Ð½Ð°Ð¿Ñ€. E 202, E 330)", foreground="gray").pack(side=tk.LEFT)

        # Ð¤Ð»Ð°Ð³Ð¸
        flags_frame = ttk.LabelFrame(scrollable_frame, text="ðŸ·ï¸ Ð¡Ð¿ÐµÑ†Ð¸Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ñ„Ð»Ð°Ð³Ð¸")
        flags_frame.pack(fill=tk.X, padx=10, pady=5)

        self.is_compound_var = tk.BooleanVar()
        ttk.Checkbutton(flags_frame, text="Ð¡Ð¾ÑÑ‚Ð°Ð²Ð½Ð¾Ð¹ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚ (ÐµÑÑ‚ÑŒ ÑÑƒÐ±-Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ñ‹)",
                        variable=self.is_compound_var).pack(anchor=tk.W, padx=5, pady=2)

        self.is_nano_var = tk.BooleanVar()
        ttk.Checkbutton(flags_frame, text="ÐÐ°Ð½Ð¾-Ð¼Ð°Ñ‚ÐµÑ€Ð¸Ð°Ð» (Ð´Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ '(nano)' Ðº Ð½Ð°Ð·Ð²Ð°Ð½Ð¸ÑŽ)",
                        variable=self.is_nano_var).pack(anchor=tk.W, padx=5, pady=2)

        self.is_oil_fat_var = tk.BooleanVar()
        ttk.Checkbutton(flags_frame, text="ÐœÐ°ÑÐ»Ð¾/Ð¶Ð¸Ñ€ (Ñ‚Ñ€ÐµÐ±ÑƒÐµÑ‚ Ð±Ð¾Ñ‚Ð°Ð½Ð¸Ñ‡ÐµÑÐºÐ¾Ðµ Ð¿Ñ€Ð¾Ð¸ÑÑ…Ð¾Ð¶Ð´ÐµÐ½Ð¸Ðµ)",
                        variable=self.is_oil_fat_var).pack(anchor=tk.W, padx=5, pady=2)

        self.is_water_var = tk.BooleanVar()
        ttk.Checkbutton(flags_frame, text="Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð½Ð°Ñ Ð²Ð¾Ð´Ð° (Ð´Ð»Ñ Ñ€Ð°ÑÑ‡Ñ‘Ñ‚Ð° Ð¿Ð¾ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ñƒ 5%)",
                        variable=self.is_water_var).pack(anchor=tk.W, padx=5, pady=2)

        # ÐšÐ½Ð¾Ð¿ÐºÐ¸ ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ
        buttons_frame = ttk.Frame(scrollable_frame)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(buttons_frame, text="ðŸ’¾ Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ",
                   command=self.save_ingredient).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="ðŸ—‘ï¸ Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ",
                   command=self.delete_ingredient).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="ðŸ§¹ ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ Ñ„Ð¾Ñ€Ð¼Ñƒ",
                   command=self.clear_editor).pack(side=tk.LEFT, padx=5)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # ============================================
    # Ð’ÐšÐ›ÐÐ”ÐšÐ 3: Ð¡ÐžÐ¡Ð¢ÐÐ’ Ð Ð•Ð¦Ð•ÐŸÐ¢Ð
    # ============================================
    def create_recipe_tab(self):
        """Ð’ÐºÐ»Ð°Ð´ÐºÐ° ÑƒÐ¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ñ ÑÐ¾ÑÑ‚Ð°Ð²Ð¾Ð¼ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="ðŸ° Ð¡Ð¾ÑÑ‚Ð°Ð² Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°")

        # Ð’Ñ‹Ð±Ð¾Ñ€ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°
        select_frame = ttk.Frame(tab)
        select_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(select_frame, text="ÐÑ€Ñ‚Ð¸ÐºÑƒÐ» Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°:").pack(side=tk.LEFT, padx=5)
        self.recipe_article_var = tk.StringVar()
        ttk.Entry(select_frame, textvariable=self.recipe_article_var, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(select_frame, text="ðŸ“¥ Ð—Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ",
                   command=self.load_recipe_ingredients).pack(side=tk.LEFT, padx=5)

        # Ð Ð°Ð·Ð´ÐµÐ»ÑÐµÐ¼ Ð½Ð° Ð´Ð²Ðµ Ñ‡Ð°ÑÑ‚Ð¸
        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Ð›ÐµÐ²Ð°Ñ Ñ‡Ð°ÑÑ‚ÑŒ: Ñ‚ÐµÐºÑƒÑ‰Ð¸Ð¹ ÑÐ¾ÑÑ‚Ð°Ð²
        left_frame = ttk.LabelFrame(paned, text="ðŸ“‹ Ð¡Ð¾ÑÑ‚Ð°Ð² Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°")
        paned.add(left_frame, weight=1)

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð² Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°
        columns = ('name', 'weight', 'quid', 'allergen')
        self.recipe_tree = ttk.Treeview(left_frame, columns=columns, show='headings', height=15)

        self.recipe_tree.heading('name', text='Ð˜Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚')
        self.recipe_tree.heading('weight', text='Ð’ÐµÑ (Ð³)')
        self.recipe_tree.heading('quid', text='QUID %')
        self.recipe_tree.heading('allergen', text='ÐÐ»Ð»ÐµÑ€Ð³ÐµÐ½')

        self.recipe_tree.column('name', width=200)
        self.recipe_tree.column('weight', width=80)
        self.recipe_tree.column('quid', width=60)
        self.recipe_tree.column('allergen', width=100)

        self.recipe_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ÐšÐ½Ð¾Ð¿ÐºÐ¸ ÑƒÐ¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ñ
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="âž– Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ",
                   command=self.remove_recipe_ingredient).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="ðŸ’¾ Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ ÑÐ¾ÑÑ‚Ð°Ð²",
                   command=self.save_recipe_ingredients).pack(side=tk.LEFT, padx=2)

        # ÐŸÑ€Ð°Ð²Ð°Ñ Ñ‡Ð°ÑÑ‚ÑŒ: Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð°
        right_frame = ttk.LabelFrame(paned, text="âž• Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚")
        paned.add(right_frame, weight=1)

        # ÐŸÐ¾Ð¸ÑÐº Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð°
        ttk.Label(right_frame, text="ÐŸÐ¾Ð¸ÑÐº:").pack(anchor=tk.W, padx=5, pady=2)
        self.recipe_search_var = tk.StringVar()
        self.recipe_search_var.trace('w', lambda *args: self.search_for_recipe())
        ttk.Entry(right_frame, textvariable=self.recipe_search_var, width=30).pack(padx=5, pady=2)

        # Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð½Ð°Ð¹Ð´ÐµÐ½Ð½Ñ‹Ñ…
        self.recipe_search_list = tk.Listbox(right_frame, height=10)
        self.recipe_search_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Ð’ÐµÑ
        weight_frame = ttk.Frame(right_frame)
        weight_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(weight_frame, text="Ð’ÐµÑ (Ð³):").pack(side=tk.LEFT)
        self.add_weight_var = tk.StringVar(value="100")
        ttk.Entry(weight_frame, textvariable=self.add_weight_var, width=10).pack(side=tk.LEFT, padx=5)

        self.add_quid_var = tk.BooleanVar()
        ttk.Checkbutton(weight_frame, text="QUID %", variable=self.add_quid_var).pack(side=tk.LEFT, padx=5)

        ttk.Button(right_frame, text="âž• Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð² Ñ€ÐµÑ†ÐµÐ¿Ñ‚",
                   command=self.add_to_recipe).pack(padx=5, pady=5)

    # ============================================
    # Ð’ÐšÐ›ÐÐ”ÐšÐ 4: Ð“Ð•ÐÐ•Ð ÐÐ¢ÐžÐ  Ð­Ð¢Ð˜ÐšÐ•Ð¢ÐžÐš
    # ============================================
    def create_label_tab(self):
        """Ð’ÐºÐ»Ð°Ð´ÐºÐ° Ð³ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ð¸ ÑÑ‚Ð¸ÐºÐµÑ‚Ð¾Ðº"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="ðŸ·ï¸ Ð­Ñ‚Ð¸ÐºÐµÑ‚ÐºÐ¸")

        # Ð’Ñ‹Ð±Ð¾Ñ€ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°
        select_frame = ttk.Frame(tab)
        select_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(select_frame, text="ÐÑ€Ñ‚Ð¸ÐºÑƒÐ»:").pack(side=tk.LEFT, padx=5)
        self.label_article_var = tk.StringVar()
        ttk.Entry(select_frame, textvariable=self.label_article_var, width=15).pack(side=tk.LEFT, padx=5)

        ttk.Label(select_frame, text="Ð’ÐµÑ Ð³Ð¾Ñ‚Ð¾Ð²Ð¾Ð³Ð¾ Ð¿Ñ€Ð¾Ð´ÑƒÐºÑ‚Ð° (Ð³):").pack(side=tk.LEFT, padx=5)
        self.final_weight_var = tk.StringVar(value="1000")
        ttk.Entry(select_frame, textvariable=self.final_weight_var, width=10).pack(side=tk.LEFT, padx=5)

        ttk.Button(select_frame, text="ðŸ”„ Ð“ÐµÐ½ÐµÑ€Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ",
                   command=self.generate_labels).pack(side=tk.LEFT, padx=10)

        # Ð¢Ñ€Ð¸ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ Ð´Ð»Ñ Ñ‚Ñ€ÐµÑ… ÑÐ·Ñ‹ÐºÐ¾Ð²
        labels_frame = ttk.Frame(tab)
        labels_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.label_texts = {}

        for i, (lang, title) in enumerate([('de', 'ðŸ‡©ðŸ‡ª Deutsch'), ('nl', 'ðŸ‡³ðŸ‡± Nederlands'), ('fr', 'ðŸ‡«ðŸ‡· FranÃ§ais')]):
            frame = ttk.LabelFrame(labels_frame, text=title)
            frame.grid(row=0, column=i, sticky='nsew', padx=5, pady=5)
            labels_frame.columnconfigure(i, weight=1)
            labels_frame.rowconfigure(0, weight=1)

            text = scrolledtext.ScrolledText(frame, width=40, height=20, wrap=tk.WORD)
            text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            self.label_texts[lang] = text

        # Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð°Ð»Ð»ÐµÑ€Ð³ÐµÐ½Ð¾Ð²
        allergens_frame = ttk.LabelFrame(tab, text="âš ï¸ ÐŸÑ€Ð¸ÑÑƒÑ‚ÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ðµ Ð°Ð»Ð»ÐµÑ€Ð³ÐµÐ½Ñ‹")
        allergens_frame.pack(fill=tk.X, padx=5, pady=5)

        self.allergens_label = ttk.Label(allergens_frame, text="", font=("Arial", 11))
        self.allergens_label.pack(padx=10, pady=5)

    # ============================================
    # WEBSOCKET
    # ============================================
    def run_websocket(self):
        """Ð—Ð°Ð¿ÑƒÑÐº WebSocket Ð² Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ"""
        self.ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.ws_loop)
        self.ws_loop.run_until_complete(self.websocket_handler())

    async def websocket_handler(self):
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚Ñ‡Ð¸Ðº WebSocket ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ñ"""
        while True:
            try:
                async with websockets.connect(SERVER_URL) as websocket:
                    self.ws = websocket
                    self.after(0, lambda: self.status_label.config(text="ðŸŸ¢ ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½"))

                    # ÐÐ²Ñ‚Ð¾Ñ€Ð¸Ð·Ð°Ñ†Ð¸Ñ
                    await websocket.send(json.dumps({
                        'type': 'auth',
                        'username': 'admin',
                        'password': 'admin123'
                    }))

                    # Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ ÑÐ¿Ñ€Ð°Ð²Ð¾Ñ‡Ð½Ð¸ÐºÐ¸
                    await websocket.send(json.dumps({'type': 'get_allergens'}))
                    await websocket.send(json.dumps({'type': 'get_additive_classes'}))
                    await websocket.send(json.dumps({'type': 'get_all_ingredients'}))

                    async for message in websocket:
                        data = json.loads(message)
                        self.after(0, lambda d=data: self.handle_message(d))

            except Exception as e:
                self.after(0, lambda: self.status_label.config(text=f"ðŸ”´ ÐžÑˆÐ¸Ð±ÐºÐ°: {e}"))
                await asyncio.sleep(5)

    def handle_message(self, data):
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ð¹ Ð¾Ñ‚ ÑÐµÑ€Ð²ÐµÑ€Ð°"""
        msg_type = data.get('type')

        if msg_type == 'auth_success':
            self.status_label.config(text="ðŸŸ¢ ÐÐ²Ñ‚Ð¾Ñ€Ð¸Ð·Ð¾Ð²Ð°Ð½")

        elif msg_type == 'allergens_list':
            self.allergens = data.get('allergens', [])
            self.update_allergen_combo()

        elif msg_type == 'additive_classes_list':
            self.additive_classes = data.get('classes', [])
            self.update_additive_combo()

        elif msg_type == 'ingredients_list':
            self.ingredients = data.get('ingredients', [])
            self.update_ingredients_list()

        elif msg_type == 'ingredient_saved':
            if data.get('success'):
                messagebox.showinfo("Ð£ÑÐ¿ÐµÑ…", data.get('message', 'Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¾'))
                self.refresh_ingredients()
            else:
                messagebox.showerror("ÐžÑˆÐ¸Ð±ÐºÐ°", data.get('error', 'ÐÐµÐ¸Ð·Ð²ÐµÑÑ‚Ð½Ð°Ñ Ð¾ÑˆÐ¸Ð±ÐºÐ°'))

        elif msg_type == 'ingredient_deleted':
            if data.get('success'):
                messagebox.showinfo("Ð£ÑÐ¿ÐµÑ…", "Ð˜Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚ ÑƒÐ´Ð°Ð»Ñ‘Ð½")
                self.refresh_ingredients()
                self.clear_editor()

        elif msg_type == 'recipe_ingredients_list':
            self.display_recipe_ingredients(data.get('ingredients', []))

        elif msg_type == 'recipe_ingredients_saved':
            if data.get('success'):
                messagebox.showinfo("Ð£ÑÐ¿ÐµÑ…", data.get('message', 'Ð¡Ð¾ÑÑ‚Ð°Ð² ÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½'))

        elif msg_type == 'zutaten_labels_all_languages':
            if data.get('success'):
                self.display_generated_labels(data)
            else:
                messagebox.showerror("ÐžÑˆÐ¸Ð±ÐºÐ°", data.get('error', 'ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ ÑÐ³ÐµÐ½ÐµÑ€Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ'))

        elif msg_type == 'ingredients_search_result':
            self.display_search_results(data.get('ingredients', []))

    # ============================================
    # ÐžÐ‘ÐÐžÐ’Ð›Ð•ÐÐ˜Ð• UI
    # ============================================
    def update_allergen_combo(self):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº Ð°Ð»Ð»ÐµÑ€Ð³ÐµÐ½Ð¾Ð² Ð² ÐºÐ¾Ð¼Ð±Ð¾Ð±Ð¾ÐºÑÐµ"""
        values = ["ÐÐµÑ‚"] + [f"{a['allergen_code']} - {a['name_de']}" for a in self.allergens]
        self.allergen_combo['values'] = values

    def update_additive_combo(self):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº ÐºÐ»Ð°ÑÑÐ¾Ð² Ð´Ð¾Ð±Ð°Ð²Ð¾Ðº Ð² ÐºÐ¾Ð¼Ð±Ð¾Ð±Ð¾ÐºÑÐµ"""
        values = ["ÐÐµÑ‚"] + [f"{c['class_code']} - {c['name_de']}" for c in self.additive_classes]
        self.additive_combo['values'] = values

    def update_ingredients_list(self):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð²"""
        self.filter_ingredients()

    def filter_ingredients(self):
        """Ð¤Ð¸Ð»ÑŒÑ‚Ñ€Ð°Ñ†Ð¸Ñ ÑÐ¿Ð¸ÑÐºÐ° Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð²"""
        # ÐžÑ‡Ð¸Ñ‰Ð°ÐµÐ¼
        for item in self.ingredients_tree.get_children():
            self.ingredients_tree.delete(item)

        search = self.search_var.get().lower()
        category = self.category_var.get()

        for ing in self.ingredients:
            # Ð¤Ð¸Ð»ÑŒÑ‚Ñ€ Ð¿Ð¾ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¸
            if category != "Ð’ÑÐµ" and ing.get('category') != category:
                continue

            # Ð¤Ð¸Ð»ÑŒÑ‚Ñ€ Ð¿Ð¾ Ð¿Ð¾Ð¸ÑÐºÑƒ
            if search:
                searchable = f"{ing.get('ingredient_code', '')} {ing.get('name_de', '')} {ing.get('name_nl', '')} {ing.get('name_fr', '')}".lower()
                if search not in searchable:
                    continue

            # ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ Ñ‚ÐµÐ³
            tag = ''
            if ing.get('allergen_code'):
                tag = 'allergen'
            elif ing.get('additive_class_code'):
                tag = 'additive'

            self.ingredients_tree.insert('', 'end', values=(
                ing.get('ingredient_code', ''),
                ing.get('name_de', ''),
                ing.get('name_nl', '') or '',
                ing.get('name_fr', '') or '',
                ing.get('category', '') or '',
                ing.get('allergen_code', '') or '',
                ing.get('additive_class_code', '') or ''
            ), tags=(tag,))

    # ============================================
    # Ð”Ð•Ð™Ð¡Ð¢Ð’Ð˜Ð¯
    # ============================================
    def refresh_ingredients(self):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð²"""
        if self.ws:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({'type': 'get_all_ingredients'})),
                self.ws_loop
            )

    def new_ingredient(self):
        """Ð¡Ð¾Ð·Ð´Ð°Ñ‚ÑŒ Ð½Ð¾Ð²Ñ‹Ð¹ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚"""
        self.clear_editor()
        self.notebook.select(1)  # ÐŸÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ð°ÐµÐ¼ÑÑ Ð½Ð° Ð²ÐºÐ»Ð°Ð´ÐºÑƒ Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¾Ñ€Ð°

    def edit_selected_ingredient(self, event=None):
        """Ð ÐµÐ´Ð°ÐºÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð½Ñ‹Ð¹ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚"""
        selection = self.ingredients_tree.selection()
        if not selection:
            return

        item = self.ingredients_tree.item(selection[0])
        code = item['values'][0]

        # ÐÐ°Ñ…Ð¾Ð´Ð¸Ð¼ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚ Ð² ÑÐ¿Ð¸ÑÐºÐµ
        for ing in self.ingredients:
            if ing.get('ingredient_code') == code:
                self.load_ingredient_to_editor(ing)
                self.notebook.select(1)  # ÐŸÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ð°ÐµÐ¼ÑÑ Ð½Ð° Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¾Ñ€
                break

    def load_ingredient_to_editor(self, ing):
        """Ð—Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚ Ð² Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¾Ñ€"""
        self.current_ingredient = ing

        self.code_var.set(ing.get('ingredient_code', ''))
        self.name_de_var.set(ing.get('name_de', ''))
        self.name_nl_var.set(ing.get('name_nl', '') or '')
        self.name_fr_var.set(ing.get('name_fr', '') or '')
        self.edit_category_var.set(ing.get('category', '') or '')

        # ÐÐ»Ð»ÐµÑ€Ð³ÐµÐ½
        if ing.get('allergen_code'):
            for a in self.allergens:
                if a['allergen_code'] == ing['allergen_code']:
                    self.allergen_var.set(f"{a['allergen_code']} - {a['name_de']}")
                    break
        else:
            self.allergen_var.set("ÐÐµÑ‚")

        # Ð”Ð¾Ð±Ð°Ð²ÐºÐ°
        if ing.get('additive_class_code'):
            for c in self.additive_classes:
                if c['class_code'] == ing['additive_class_code']:
                    self.additive_class_var.set(f"{c['class_code']} - {c['name_de']}")
                    break
        else:
            self.additive_class_var.set("ÐÐµÑ‚")

        self.e_number_var.set(ing.get('e_number', '') or '')
        self.is_compound_var.set(ing.get('is_compound', False))
        self.is_nano_var.set(ing.get('is_nano', False))
        self.is_oil_fat_var.set(ing.get('is_oil_fat', False))
        self.is_water_var.set(ing.get('is_added_water', False))

    def clear_editor(self):
        """ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ Ñ„Ð¾Ñ€Ð¼Ñƒ Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¾Ñ€Ð°"""
        self.current_ingredient = None
        self.code_var.set('')
        self.name_de_var.set('')
        self.name_nl_var.set('')
        self.name_fr_var.set('')
        self.edit_category_var.set('')
        self.allergen_var.set('ÐÐµÑ‚')
        self.additive_class_var.set('ÐÐµÑ‚')
        self.e_number_var.set('')
        self.is_compound_var.set(False)
        self.is_nano_var.set(False)
        self.is_oil_fat_var.set(False)
        self.is_water_var.set(False)

    def save_ingredient(self):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚"""
        if not self.code_var.get() or not self.name_de_var.get():
            messagebox.showerror("ÐžÑˆÐ¸Ð±ÐºÐ°", "ÐšÐ¾Ð´ Ð¸ Ð½Ð°Ð·Ð²Ð°Ð½Ð¸Ðµ (DE) Ð¾Ð±ÑÐ·Ð°Ñ‚ÐµÐ»ÑŒÐ½Ñ‹!")
            return

        # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ allergen_id
        allergen_id = None
        allergen_val = self.allergen_var.get()
        if allergen_val != "ÐÐµÑ‚":
            code = allergen_val.split(" - ")[0]
            for a in self.allergens:
                if a['allergen_code'] == code:
                    allergen_id = a['allergen_id']
                    break

        # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ additive_class_id
        additive_class_id = None
        additive_val = self.additive_class_var.get()
        if additive_val != "ÐÐµÑ‚":
            code = additive_val.split(" - ")[0]
            for c in self.additive_classes:
                if c['class_code'] == code:
                    additive_class_id = c['class_id']
                    break

        data = {
            'type': 'save_ingredient',
            'ingredient_code': self.code_var.get(),
            'name_de': self.name_de_var.get(),
            'name_nl': self.name_nl_var.get() or None,
            'name_fr': self.name_fr_var.get() or None,
            'category': self.edit_category_var.get() or None,
            'allergen_id': allergen_id,
            'additive_class_id': additive_class_id,
            'e_number': self.e_number_var.get() or None,
            'is_compound': self.is_compound_var.get(),
            'is_nano': self.is_nano_var.get(),
            'is_oil_fat': self.is_oil_fat_var.get(),
            'is_added_water': self.is_water_var.get(),
        }

        # Ð•ÑÐ»Ð¸ Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¸Ñ€ÑƒÐµÐ¼ ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ð¹
        if self.current_ingredient:
            data['ingredient_id'] = self.current_ingredient.get('ingredient_id')

        if self.ws:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps(data)),
                self.ws_loop
            )

    def delete_ingredient(self):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚"""
        if not self.current_ingredient:
            messagebox.showwarning("Ð’Ð½Ð¸Ð¼Ð°Ð½Ð¸Ðµ", "Ð¡Ð½Ð°Ñ‡Ð°Ð»Ð° Ð²Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚")
            return

        if messagebox.askyesno("ÐŸÐ¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð¸Ðµ", "Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÑÑ‚Ð¾Ñ‚ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚?"):
            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self.ws.send(json.dumps({
                        'type': 'delete_ingredient',
                        'ingredient_id': self.current_ingredient['ingredient_id']
                    })),
                    self.ws_loop
                )

    # ============================================
    # Ð Ð•Ð¦Ð•ÐŸÐ¢Ð«
    # ============================================
    def load_recipe_ingredients(self):
        """Ð—Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ñ‹ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°"""
        article = self.recipe_article_var.get()
        if not article:
            messagebox.showwarning("Ð’Ð½Ð¸Ð¼Ð°Ð½Ð¸Ðµ", "Ð’Ð²ÐµÐ´Ð¸Ñ‚Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°")
            return

        if self.ws:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({
                    'type': 'get_recipe_ingredients',
                    'article_nr': article
                })),
                self.ws_loop
            )

    def display_recipe_ingredients(self, ingredients):
        """ÐžÑ‚Ð¾Ð±Ñ€Ð°Ð·Ð¸Ñ‚ÑŒ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ñ‹ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°"""
        for item in self.recipe_tree.get_children():
            self.recipe_tree.delete(item)

        for ing in ingredients:
            self.recipe_tree.insert('', 'end', values=(
                ing.get('name_de', ''),
                ing.get('weight_grams', 0),
                'âœ“' if ing.get('highlight_quid') else '',
                ing.get('allergen_code', '') or ''
            ), iid=str(ing.get('ingredient_id')))

    def search_for_recipe(self):
        """ÐŸÐ¾Ð¸ÑÐº Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð² Ð´Ð»Ñ Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¸Ñ Ð² Ñ€ÐµÑ†ÐµÐ¿Ñ‚"""
        query = self.recipe_search_var.get()
        if len(query) < 2:
            return

        if self.ws:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({
                    'type': 'search_ingredients',
                    'query': query,
                    'limit': 20
                })),
                self.ws_loop
            )

    def display_search_results(self, ingredients):
        """ÐžÑ‚Ð¾Ð±Ñ€Ð°Ð·Ð¸Ñ‚ÑŒ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ñ‹ Ð¿Ð¾Ð¸ÑÐºÐ°"""
        self.recipe_search_list.delete(0, tk.END)
        self._search_results = ingredients

        for ing in ingredients:
            self.recipe_search_list.insert(tk.END,
                f"{ing['ingredient_code']} - {ing['name_de']}")

    def add_to_recipe(self):
        """Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚ Ð² Ñ€ÐµÑ†ÐµÐ¿Ñ‚"""
        selection = self.recipe_search_list.curselection()
        if not selection:
            messagebox.showwarning("Ð’Ð½Ð¸Ð¼Ð°Ð½Ð¸Ðµ", "Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚ Ð¸Ð· ÑÐ¿Ð¸ÑÐºÐ°")
            return

        ing = self._search_results[selection[0]]
        weight = self.add_weight_var.get()

        try:
            weight = float(weight)
        except ValueError:
            messagebox.showerror("ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð’Ð²ÐµÐ´Ð¸Ñ‚Ðµ ÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ñ‹Ð¹ Ð²ÐµÑ")
            return

        # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð² Ð´ÐµÑ€ÐµÐ²Ð¾
        self.recipe_tree.insert('', 'end', values=(
            ing.get('name_de', ''),
            weight,
            'âœ“' if self.add_quid_var.get() else '',
            ing.get('allergen_code', '') or ''
        ), iid=str(ing.get('ingredient_id')))

    def remove_recipe_ingredient(self):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚ Ð¸Ð· Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°"""
        selection = self.recipe_tree.selection()
        if selection:
            self.recipe_tree.delete(selection[0])

    def save_recipe_ingredients(self):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ ÑÐ¾ÑÑ‚Ð°Ð² Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°"""
        article = self.recipe_article_var.get()
        if not article:
            messagebox.showwarning("Ð’Ð½Ð¸Ð¼Ð°Ð½Ð¸Ðµ", "Ð’Ð²ÐµÐ´Ð¸Ñ‚Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°")
            return

        ingredients = []
        for item_id in self.recipe_tree.get_children():
            item = self.recipe_tree.item(item_id)
            values = item['values']
            ingredients.append({
                'ingredient_id': int(item_id),
                'weight_grams': float(values[1]),
                'highlight_quid': values[2] == 'âœ“'
            })

        if self.ws:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({
                    'type': 'save_recipe_ingredients',
                    'article_nr': article,
                    'ingredients': ingredients
                })),
                self.ws_loop
            )

    # ============================================
    # Ð“Ð•ÐÐ•Ð ÐÐ¦Ð˜Ð¯ Ð­Ð¢Ð˜ÐšÐ•Ð¢ÐžÐš
    # ============================================
    def generate_labels(self):
        """Ð“ÐµÐ½ÐµÑ€Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ ÑÑ‚Ð¸ÐºÐµÑ‚ÐºÐ¸ Ð½Ð° Ð²ÑÐµÑ… ÑÐ·Ñ‹ÐºÐ°Ñ…"""
        article = self.label_article_var.get()
        if not article:
            messagebox.showwarning("Ð’Ð½Ð¸Ð¼Ð°Ð½Ð¸Ðµ", "Ð’Ð²ÐµÐ´Ð¸Ñ‚Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»")
            return

        try:
            final_weight = float(self.final_weight_var.get())
        except ValueError:
            messagebox.showerror("ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð’Ð²ÐµÐ´Ð¸Ñ‚Ðµ ÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ñ‹Ð¹ Ð²ÐµÑ")
            return

        if self.ws:
            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({
                    'type': 'generate_all_languages',
                    'article_nr': article,
                    'final_weight_grams': final_weight
                })),
                self.ws_loop
            )

    def display_generated_labels(self, data):
        """ÐžÑ‚Ð¾Ð±Ñ€Ð°Ð·Ð¸Ñ‚ÑŒ ÑÐ³ÐµÐ½ÐµÑ€Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ñ‹Ðµ ÑÑ‚Ð¸ÐºÐµÑ‚ÐºÐ¸"""
        labels = data.get('labels', {})

        for lang in ['de', 'nl', 'fr']:
            text_widget = self.label_texts[lang]
            text_widget.delete('1.0', tk.END)

            if lang in labels:
                label_text = labels[lang].get('label_text', '')
                # Ð—Ð°Ð¼ÐµÐ½ÑÐµÐ¼ **bold** Ð½Ð° Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ñ‚ÐµÐºÑÑ‚ Ð´Ð»Ñ Ð¾Ñ‚Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½Ð¸Ñ
                label_text = label_text.replace('**', '')
                text_widget.insert('1.0', label_text)

        # ÐŸÐ¾ÐºÐ°Ð·Ñ‹Ð²Ð°ÐµÐ¼ Ð°Ð»Ð»ÐµÑ€Ð³ÐµÐ½Ñ‹
        allergens = labels.get('de', {}).get('allergens_present', [])
        if allergens:
            self.allergens_label.config(
                text=", ".join(allergens),
                foreground="red"
            )
        else:
            self.allergens_label.config(text="ÐÐµÑ‚", foreground="green")

    # ============================================
    # Ð—ÐÐšÐ Ð«Ð¢Ð˜Ð•
    # ============================================
    def on_closing(self):
        """Ð—Ð°ÐºÑ€Ñ‹Ñ‚Ð¸Ðµ Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ"""
        if self.ws_loop:
            self.ws_loop.call_soon_threadsafe(self.ws_loop.stop)
        self.destroy()


# ============================================
# Ð—ÐÐŸÐ£Ð¡Ðš
# ============================================
if __name__ == "__main__":
    app = ZutatenAdminPanel()
    app.mainloop()
