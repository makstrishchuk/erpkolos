#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÐÐ”ÐœÐ˜Ð-ÐŸÐÐÐ•Ð›Ð¬ Ð¡ GUI
ÐŸÐ¾Ð»Ð½Ñ‹Ð¹ ÐºÐ¾Ð½Ñ‚Ñ€Ð¾Ð»ÑŒ Ð½Ð°Ð´ ÑÐ¸ÑÑ‚ÐµÐ¼Ð¾Ð¹:
- ÐŸÑ€Ð¾ÑÐ¼Ð¾Ñ‚Ñ€ Ð²ÑÐµÑ… Ð·Ð°ÐºÐ°Ð·Ð¾Ð² Ð¸ Ð¸Ñ… ÑÑ‚Ð°Ñ‚ÑƒÑÐ¾Ð²
- Ð£Ð´Ð°Ð»ÐµÐ½Ð¸Ðµ/Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
- ÐŸÑ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð°Ñ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ Ð½Ð° Ð»ÑŽÐ±Ð¾Ð¼ ÑÐºÐ»Ð°Ð´Ðµ
- Ð–ÑƒÑ€Ð½Ð°Ð» Ð¾ÑˆÐ¸Ð±Ð¾Ðº
- Ð¡Ñ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ° Ð¸ Ð¾Ñ‚Ñ‡ÐµÑ‚Ñ‹
- Ð£Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐ¸ÑÑ‚ÐµÐ¼Ð¾Ð¹
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import asyncio
import websockets
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

# ============================================
# ÐÐÐ¡Ð¢Ð ÐžÐ™ÐšÐ˜
# ============================================
SERVER_URL = "ws://server01:8080/ws/admin"

# ============================================
# GUI ÐÐ”ÐœÐ˜Ð-ÐŸÐÐÐ•Ð›Ð¬
# ============================================
class AdminPanel(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("ðŸ” ÐÐ”ÐœÐ˜Ð-ÐŸÐÐÐ•Ð›Ð¬ - WISO GoLabel")
        self.geometry("1600x900")

        self.orders = {}
        self.errors = []
        self.statistics = {}
        self.ws = None
        self.ws_loop = None

        # Zutaten V2 Ð´Ð°Ð½Ð½Ñ‹Ðµ
        self.ingredients = []
        self.allergens = []
        self.additive_classes = []
        self.current_ingredient = None
        self._search_results = []

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

        ttk.Label(header, text="ðŸ” ÐŸÐÐÐ•Ð›Ð¬ ÐÐ”ÐœÐ˜ÐÐ˜Ð¡Ð¢Ð ÐÐ¢ÐžÐ Ð", font=("Arial", 18, "bold")).pack(side=tk.LEFT)

        self.status_label = ttk.Label(header, text="âšª ÐžÑ‚ÐºÐ»ÑŽÑ‡ÐµÐ½", font=("Arial", 12))
        self.status_label.pack(side=tk.RIGHT)

        # Ð¡Ñ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ°
        stats_frame = ttk.LabelFrame(self, text="ðŸ“Š Ð¡Ñ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ° Ð¡Ð¸ÑÑ‚ÐµÐ¼Ñ‹")
        stats_frame.pack(fill=tk.X, padx=10, pady=5)

        self.stats_labels = {}
        stats_items = [
            ('total_orders', 'Ð’ÑÐµÐ³Ð¾ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²'),
            ('successful', 'Ð£ÑÐ¿ÐµÑˆÐ½Ñ‹Ñ…'),
            ('failed', 'ÐžÑˆÐ¸Ð±Ð¾Ðº'),
            ('ftp_sent', 'ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¾ FTP')
        ]

        for i, (key, label) in enumerate(stats_items):
            ttk.Label(stats_frame, text=f"{label}:").grid(row=0, column=i*2, padx=10, pady=5, sticky=tk.W)
            self.stats_labels[key] = ttk.Label(stats_frame, text="0", font=("Arial", 14, "bold"), foreground="blue")
            self.stats_labels[key].grid(row=0, column=i*2+1, padx=10, pady=5, sticky=tk.W)

        # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ notebook (Ð²ÐºÐ»Ð°Ð´ÐºÐ¸)
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # ===== Ð’ÐšÐ›ÐÐ”ÐšÐ 1: Ð—ÐÐšÐÐ—Ð« =====
        orders_tab = ttk.Frame(notebook)
        notebook.add(orders_tab, text="ðŸ“¦ Ð—Ð°ÐºÐ°Ð·Ñ‹")

        # ÐŸÐ°Ð½ÐµÐ»ÑŒ ÑƒÐ¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ñ Ð·Ð°ÐºÐ°Ð·Ð°Ð¼Ð¸
        orders_control = ttk.Frame(orders_tab)
        orders_control.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(orders_control, text="ðŸ”„ ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ", command=self.refresh_orders).pack(side=tk.LEFT, padx=2)
        ttk.Button(orders_control, text="ðŸ—‘ï¸ Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð½Ñ‹Ð¹", command=self.delete_selected_order).pack(side=tk.LEFT, padx=2)
        ttk.Button(orders_control, text="ðŸ–¨ï¸ ÐŸÑ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð°Ñ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ", command=self.force_print_order).pack(side=tk.LEFT, padx=2)
        ttk.Button(orders_control, text="ðŸ” ÐŸÐµÑ€ÐµÐ·Ð°Ð¿ÑƒÑÑ‚Ð¸Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð·", command=self.restart_order).pack(side=tk.LEFT, padx=2)
        ttk.Button(orders_control, text="ðŸ“‹ Ð”ÐµÑ‚Ð°Ð»Ð¸ Ð·Ð°ÐºÐ°Ð·Ð°", command=self.show_order_details).pack(side=tk.LEFT, padx=2)

        # Ð¤Ð¸Ð»ÑŒÑ‚Ñ€
        ttk.Label(orders_control, text="  |  Ð¤Ð¸Ð»ÑŒÑ‚Ñ€:").pack(side=tk.LEFT, padx=5)
        self.filter_var = tk.StringVar(value="all")
        ttk.Radiobutton(orders_control, text="Ð’ÑÐµ", variable=self.filter_var, value="all", command=self.apply_filter).pack(side=tk.LEFT)
        ttk.Radiobutton(orders_control, text="ÐÐºÑ‚Ð¸Ð²Ð½Ñ‹Ðµ", variable=self.filter_var, value="active", command=self.apply_filter).pack(side=tk.LEFT)
        ttk.Radiobutton(orders_control, text="Ð—Ð°Ð²ÐµÑ€ÑˆÐµÐ½Ð½Ñ‹Ðµ", variable=self.filter_var, value="completed", command=self.apply_filter).pack(side=tk.LEFT)
        ttk.Radiobutton(orders_control, text="ÐžÑˆÐ¸Ð±ÐºÐ¸", variable=self.filter_var, value="error", command=self.apply_filter).pack(side=tk.LEFT)

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
        columns = ('order_id', 'customer', 'status', 'labels', 'invoice', 'ftp', 'warehouse', 'created', 'printed')
        self.orders_tree = ttk.Treeview(orders_tab, columns=columns, show='headings', height=20)

        self.orders_tree.heading('order_id', text='ID Ð—Ð°ÐºÐ°Ð·Ð°')
        self.orders_tree.heading('customer', text='ÐšÐ»Ð¸ÐµÐ½Ñ‚')
        self.orders_tree.heading('status', text='Ð¡Ñ‚Ð°Ñ‚ÑƒÑ')
        self.orders_tree.heading('labels', text='Ð­Ñ‚Ð¸ÐºÐµÑ‚ÐºÐ¸')
        self.orders_tree.heading('invoice', text='Ð¡Ñ‡ÐµÑ‚')
        self.orders_tree.heading('ftp', text='FTP')
        self.orders_tree.heading('warehouse', text='Ð¡ÐºÐ»Ð°Ð´')
        self.orders_tree.heading('created', text='Ð¡Ð¾Ð·Ð´Ð°Ð½')
        self.orders_tree.heading('printed', text='ÐÐ°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½')

        self.orders_tree.column('order_id', width=100, anchor=tk.CENTER)
        self.orders_tree.column('customer', width=180)
        self.orders_tree.column('status', width=120, anchor=tk.CENTER)
        self.orders_tree.column('labels', width=100, anchor=tk.CENTER)
        self.orders_tree.column('invoice', width=100, anchor=tk.CENTER)
        self.orders_tree.column('ftp', width=80, anchor=tk.CENTER)
        self.orders_tree.column('warehouse', width=100, anchor=tk.CENTER)
        self.orders_tree.column('created', width=140, anchor=tk.CENTER)
        self.orders_tree.column('printed', width=140, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(orders_tab, orient=tk.VERTICAL, command=self.orders_tree.yview)
        self.orders_tree.configure(yscroll=scrollbar.set)

        self.orders_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        # Ð¦Ð²ÐµÑ‚Ð¾Ð²Ñ‹Ðµ Ñ‚ÐµÐ³Ð¸
        self.orders_tree.tag_configure('completed', background='#C8E6C9')
        self.orders_tree.tag_configure('error', background='#FFCDD2')
        self.orders_tree.tag_configure('processing', background='#B3E5FC')
        self.orders_tree.tag_configure('printing', background='#E1BEE7')

        # ===== Ð’ÐšÐ›ÐÐ”ÐšÐ 2: ÐžÐ¨Ð˜Ð‘ÐšÐ˜ =====
        errors_tab = ttk.Frame(notebook)
        notebook.add(errors_tab, text="âš ï¸ ÐžÑˆÐ¸Ð±ÐºÐ¸")

        # ÐŸÐ°Ð½ÐµÐ»ÑŒ ÑƒÐ¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ñ Ð¾ÑˆÐ¸Ð±ÐºÐ°Ð¼Ð¸
        errors_control = ttk.Frame(errors_tab)
        errors_control.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(errors_control, text="ðŸ”„ ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ", command=self.refresh_errors).pack(side=tk.LEFT, padx=2)
        ttk.Button(errors_control, text="ðŸ—‘ï¸ ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ð¾ÑˆÐ¸Ð±ÐºÐ¸", command=self.clear_all_errors).pack(side=tk.LEFT, padx=2)

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¾ÑˆÐ¸Ð±Ð¾Ðº
        error_columns = ('time', 'order_id', 'type', 'message')
        self.errors_tree = ttk.Treeview(errors_tab, columns=error_columns, show='headings', height=25)

        self.errors_tree.heading('time', text='Ð’Ñ€ÐµÐ¼Ñ')
        self.errors_tree.heading('order_id', text='Ð—Ð°ÐºÐ°Ð·')
        self.errors_tree.heading('type', text='Ð¢Ð¸Ð¿')
        self.errors_tree.heading('message', text='Ð¡Ð¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð¾Ð± Ð¾ÑˆÐ¸Ð±ÐºÐµ')

        self.errors_tree.column('time', width=140, anchor=tk.CENTER)
        self.errors_tree.column('order_id', width=100, anchor=tk.CENTER)
        self.errors_tree.column('type', width=150)
        self.errors_tree.column('message', width=600)

        error_scrollbar = ttk.Scrollbar(errors_tab, orient=tk.VERTICAL, command=self.errors_tree.yview)
        self.errors_tree.configure(yscroll=error_scrollbar.set)

        self.errors_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        error_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        # ===== Ð’ÐšÐ›ÐÐ”ÐšÐ 3: ÐžÐ¢Ð§Ð•Ð¢Ð« =====
        reports_tab = ttk.Frame(notebook)
        notebook.add(reports_tab, text="ðŸ“Š ÐžÑ‚Ñ‡ÐµÑ‚Ñ‹")

        ttk.Label(reports_tab, text="ðŸ“… ÐžÑ‚Ñ‡ÐµÑ‚ Ð¿Ð¾ Ð´Ð½ÑÐ¼", font=("Arial", 14, "bold")).pack(pady=10)

        # ÐŸÐ°Ð½ÐµÐ»ÑŒ Ð²Ñ‹Ð±Ð¾Ñ€Ð° Ð¿ÐµÑ€Ð¸Ð¾Ð´Ð°
        period_frame = ttk.Frame(reports_tab)
        period_frame.pack(fill=tk.X, padx=20, pady=10)

        ttk.Label(period_frame, text="ÐŸÐµÑ€Ð¸Ð¾Ð´:").pack(side=tk.LEFT, padx=5)
        self.report_period = tk.StringVar(value="today")
        ttk.Radiobutton(period_frame, text="Ð¡ÐµÐ³Ð¾Ð´Ð½Ñ", variable=self.report_period, value="today", command=self.generate_report).pack(side=tk.LEFT)
        ttk.Radiobutton(period_frame, text="Ð’Ñ‡ÐµÑ€Ð°", variable=self.report_period, value="yesterday", command=self.generate_report).pack(side=tk.LEFT)
        ttk.Radiobutton(period_frame, text="Ð—Ð° Ð½ÐµÐ´ÐµÐ»ÑŽ", variable=self.report_period, value="week", command=self.generate_report).pack(side=tk.LEFT)
        ttk.Radiobutton(period_frame, text="Ð—Ð° Ð¼ÐµÑÑÑ†", variable=self.report_period, value="month", command=self.generate_report).pack(side=tk.LEFT)

        ttk.Button(period_frame, text="ðŸ“¥ Ð­ÐºÑÐ¿Ð¾Ñ€Ñ‚ Ð² Ñ„Ð°Ð¹Ð»", command=self.export_report).pack(side=tk.RIGHT, padx=5)

        # Ð¢ÐµÐºÑÑ‚ Ð¾Ñ‚Ñ‡ÐµÑ‚Ð°
        self.report_text = scrolledtext.ScrolledText(reports_tab, height=30, wrap=tk.WORD, font=("Consolas", 10))
        self.report_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # ===== Ð’ÐšÐ›ÐÐ”ÐšÐ 4: Ð–Ð£Ð ÐÐÐ› =====
        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="ðŸ“œ Ð–ÑƒÑ€Ð½Ð°Ð»")

        log_control = ttk.Frame(log_tab)
        log_control.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(log_control, text="ðŸ—‘ï¸ ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ Ð¶ÑƒÑ€Ð½Ð°Ð»", command=self.clear_log).pack(side=tk.LEFT, padx=2)

        self.log_text = scrolledtext.ScrolledText(log_tab, height=30, wrap=tk.WORD, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("info", foreground="blue")
        self.log_text.tag_config("warning", foreground="orange")

    def log_message(self, message, tag="normal"):
        """Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ Ð² Ð»Ð¾Ð³"""
        self.log_text.configure(state='normal')
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')

    def clear_log(self):
        """ÐžÑ‡Ð¸ÑÑ‚ÐºÐ° Ð¶ÑƒÑ€Ð½Ð°Ð»Ð°"""
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state='disabled')

    def update_statistics(self, stats):
        """ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ¸"""
        self.statistics = stats
        self.stats_labels['total_orders'].config(text=str(stats.get('total_orders', 0)))
        self.stats_labels['successful'].config(text=str(stats.get('successful', 0)))
        self.stats_labels['failed'].config(text=str(stats.get('failed', 0)))
        self.stats_labels['ftp_sent'].config(text=str(stats.get('ftp_sent', 0)))

    def update_order_in_tree(self, order_data):
        """ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ Ð·Ð°ÐºÐ°Ð·Ð° Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ðµ"""
        order_id = order_data.get('order_id')

        status = order_data.get('status', 'pending')
        tag = 'completed' if status == 'completed' else 'error' if 'error' in status else 'processing'

        created_at = order_data.get('created_at', '')
        try:
            dt = datetime.fromisoformat(created_at)
            created_str = dt.strftime('%Y-%m-%d %H:%M')
        except:
            created_str = 'N/A'

        printed_at = order_data.get('printed_at', '')
        printed_str = 'N/A'
        if order_data.get('printed'):
            try:
                if printed_at:
                    dt = datetime.fromisoformat(printed_at)
                    printed_str = dt.strftime('%Y-%m-%d %H:%M')
                else:
                    printed_str = 'âœ…'
            except:
                printed_str = 'âœ…'

        values = (
            order_id,
            order_data.get('customer', 'N/A'),
            self.translate_status(status),
            order_data.get('labels_status', 'â³'),
            order_data.get('invoice_status', 'N/A'),
            order_data.get('ftp_status', 'N/A'),
            order_data.get('warehouse', 'N/A'),
            created_str,
            printed_str
        )

        if order_id in self.orders:
            item_id = self.orders[order_id]['item_id']
            self.orders_tree.item(item_id, values=values, tags=(tag,))
            self.orders[order_id]['data'] = order_data
        else:
            item_id = self.orders_tree.insert('', 0, values=values, tags=(tag,))
            self.orders[order_id] = {'item_id': item_id, 'data': order_data}

    def translate_status(self, status):
        """ÐŸÐµÑ€ÐµÐ²Ð¾Ð´ ÑÑ‚Ð°Ñ‚ÑƒÑÐ°"""
        translations = {
            'pending': 'â³ ÐžÐ¶Ð¸Ð´Ð°Ð½Ð¸Ðµ',
            'processing': 'ðŸ”„ ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ°',
            'processing_invoice': 'ðŸ“„ Ð¡Ñ‡ÐµÑ‚',
            'ready_to_print': 'ðŸ–¨ï¸ Ð“Ð¾Ñ‚Ð¾Ð² Ðº Ð¿ÐµÑ‡Ð°Ñ‚Ð¸',
            'printing': 'ðŸ–¨ï¸ ÐŸÐµÑ‡Ð°Ñ‚ÑŒ',
            'completed': 'âœ… Ð“Ð¾Ñ‚Ð¾Ð²Ð¾',
            'error': 'âŒ ÐžÑˆÐ¸Ð±ÐºÐ°',
            'print_error': 'âŒ ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿ÐµÑ‡Ð°Ñ‚Ð¸'
        }
        return translations.get(status, status)

    def apply_filter(self):
        """ÐŸÑ€Ð¸Ð¼ÐµÐ½Ð¸Ñ‚ÑŒ Ñ„Ð¸Ð»ÑŒÑ‚Ñ€"""
        filter_value = self.filter_var.get()

        for order_id, order_info in self.orders.items():
            item_id = order_info['item_id']
            order_data = order_info['data']
            status = order_data.get('status', '')

            if filter_value == "all":
                show = True
            elif filter_value == "active":
                show = status not in ['completed', 'error', 'print_error']
            elif filter_value == "completed":
                show = status == 'completed'
            elif filter_value == "error":
                show = 'error' in status
            else:
                show = True

            if show:
                try:
                    self.orders_tree.reattach(item_id, '', 0)
                except:
                    pass
            else:
                try:
                    self.orders_tree.detach(item_id)
                except:
                    pass

    def refresh_orders(self):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº Ð·Ð°ÐºÐ°Ð·Ð¾Ð²"""
        self.log_message("ðŸ”„ ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐ¿Ð¸ÑÐºÐ° Ð·Ð°ÐºÐ°Ð·Ð¾Ð²...", "info")
        # Ð—Ð°ÐºÐ°Ð·Ñ‹ Ð¾Ð±Ð½Ð¾Ð²Ð»ÑÑŽÑ‚ÑÑ Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ Ñ‡ÐµÑ€ÐµÐ· WebSocket

    def delete_selected_order(self):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð½Ñ‹Ð¹ Ð·Ð°ÐºÐ°Ð·"""
        selected = self.orders_tree.selection()
        if not selected:
            messagebox.showwarning("Ð’Ð½Ð¸Ð¼Ð°Ð½Ð¸Ðµ", "Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ð·Ð°ÐºÐ°Ð· Ð´Ð»Ñ ÑƒÐ´Ð°Ð»ÐµÐ½Ð¸Ñ")
            return

        result = messagebox.askyesno("Ð£Ð´Ð°Ð»ÐµÐ½Ð¸Ðµ", "Ð’Ñ‹ ÑƒÐ²ÐµÑ€ÐµÐ½Ñ‹, Ñ‡Ñ‚Ð¾ Ñ…Ð¾Ñ‚Ð¸Ñ‚Ðµ ÑƒÐ´Ð°Ð»Ð¸Ñ‚ÑŒ ÑÑ‚Ð¾Ñ‚ Ð·Ð°ÐºÐ°Ð·?\n\nÐ­Ñ‚Ð¾ Ð´ÐµÐ¹ÑÑ‚Ð²Ð¸Ðµ Ð½ÐµÐ¾Ð±Ñ€Ð°Ñ‚Ð¸Ð¼Ð¾!")
        if not result:
            return

        for item_id in selected:
            values = self.orders_tree.item(item_id)['values']
            order_id = values[0]

            self.orders_tree.delete(item_id)
            if order_id in self.orders:
                del self.orders[order_id]

            self.log_message(f"ðŸ—‘ï¸ Ð£Ð´Ð°Ð»ÐµÐ½ Ð·Ð°ÐºÐ°Ð·: {order_id}", "warning")

    def force_print_order(self):
        """ÐŸÑ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð°Ñ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð·Ð° Ð½Ð° ÑÐºÐ»Ð°Ð´Ðµ"""
        selected = self.orders_tree.selection()
        if not selected:
            messagebox.showwarning("Ð’Ð½Ð¸Ð¼Ð°Ð½Ð¸Ðµ", "Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ð·Ð°ÐºÐ°Ð· Ð´Ð»Ñ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸")
            return

        warehouse_id = simpledialog.askstring("Ð¡ÐºÐ»Ð°Ð´", "Ð’Ð²ÐµÐ´Ð¸Ñ‚Ðµ ID ÑÐºÐ»Ð°Ð´Ð° (Ð½Ð°Ð¿Ñ€Ð¸Ð¼ÐµÑ€: WAREHOUSE_1):")
        if not warehouse_id:
            return

        for item_id in selected:
            values = self.orders_tree.item(item_id)['values']
            order_id = values[0]

            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_server({
                        'type': 'force_print',
                        'order_id': order_id,
                        'warehouse_id': warehouse_id
                    }),
                    self.ws_loop
                )

            self.log_message(f"ðŸ–¨ï¸ ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð¼Ð°Ð½Ð´Ð° Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ Ð·Ð°ÐºÐ°Ð·Ð° {order_id} Ð½Ð° {warehouse_id}", "info")

    def restart_order(self):
        """ÐŸÐµÑ€ÐµÐ·Ð°Ð¿ÑƒÑÑ‚Ð¸Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð·"""
        selected = self.orders_tree.selection()
        if not selected:
            messagebox.showwarning("Ð’Ð½Ð¸Ð¼Ð°Ð½Ð¸Ðµ", "Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ð·Ð°ÐºÐ°Ð· Ð´Ð»Ñ Ð¿ÐµÑ€ÐµÐ·Ð°Ð¿ÑƒÑÐºÐ°")
            return

        for item_id in selected:
            values = self.orders_tree.item(item_id)['values']
            order_id = values[0]

            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_server({
                        'type': 'restart_order',
                        'order_id': order_id
                    }),
                    self.ws_loop
                )

            self.log_message(f"ðŸ” ÐŸÐµÑ€ÐµÐ·Ð°Ð¿ÑƒÑ‰ÐµÐ½ Ð·Ð°ÐºÐ°Ð·: {order_id}", "info")

    def show_order_details(self):
        """ÐŸÐ¾ÐºÐ°Ð·Ð°Ñ‚ÑŒ Ð´ÐµÑ‚Ð°Ð»Ð¸ Ð·Ð°ÐºÐ°Ð·Ð°"""
        selected = self.orders_tree.selection()
        if not selected:
            messagebox.showwarning("Ð’Ð½Ð¸Ð¼Ð°Ð½Ð¸Ðµ", "Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ð·Ð°ÐºÐ°Ð·")
            return

        item_id = selected[0]
        values = self.orders_tree.item(item_id)['values']
        order_id = values[0]

        if order_id in self.orders:
            order_data = self.orders[order_id]['data']
            details = json.dumps(order_data, indent=2, ensure_ascii=False)

            detail_window = tk.Toplevel(self)
            detail_window.title(f"Ð”ÐµÑ‚Ð°Ð»Ð¸ Ð·Ð°ÐºÐ°Ð·Ð° {order_id}")
            detail_window.geometry("600x700")

            text = scrolledtext.ScrolledText(detail_window, wrap=tk.WORD, font=("Consolas", 10))
            text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            text.insert(1.0, details)
            text.configure(state='disabled')

    def refresh_errors(self):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº Ð¾ÑˆÐ¸Ð±Ð¾Ðº"""
        self.errors_tree.delete(*self.errors_tree.get_children())

        for error in self.errors:
            values = (
                error.get('timestamp', ''),
                error.get('order_id', 'N/A'),
                error.get('type', 'Unknown'),
                error.get('error', 'No description')
            )
            self.errors_tree.insert('', 0, values=values)

    def clear_all_errors(self):
        """ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ð¾ÑˆÐ¸Ð±ÐºÐ¸"""
        result = messagebox.askyesno("ÐžÑ‡Ð¸ÑÑ‚ÐºÐ°", "ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ð¾ÑˆÐ¸Ð±ÐºÐ¸?")
        if result:
            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_server({'type': 'clear_errors'}),
                    self.ws_loop
                )

            self.errors.clear()
            self.errors_tree.delete(*self.errors_tree.get_children())
            self.log_message("ðŸ—‘ï¸ Ð’ÑÐµ Ð¾ÑˆÐ¸Ð±ÐºÐ¸ Ð¾Ñ‡Ð¸Ñ‰ÐµÐ½Ñ‹", "success")

    def generate_report(self):
        """Ð“ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ñ Ð¾Ñ‚Ñ‡ÐµÑ‚Ð°"""
        period = self.report_period.get()
        now = datetime.now()

        # Ð¤Ð¸Ð»ÑŒÑ‚Ñ€ÑƒÐµÐ¼ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ð¿Ð¾ Ð¿ÐµÑ€Ð¸Ð¾Ð´Ñƒ
        filtered_orders = []

        for order_id, order_info in self.orders.items():
            order_data = order_info['data']
            try:
                created_at = datetime.fromisoformat(order_data.get('created_at', ''))

                if period == "today":
                    include = created_at.date() == now.date()
                elif period == "yesterday":
                    include = created_at.date() == (now.date() - timedelta(days=1))
                elif period == "week":
                    include = (now - created_at).days <= 7
                elif period == "month":
                    include = (now - created_at).days <= 30
                else:
                    include = True

                if include:
                    filtered_orders.append(order_data)
            except:
                pass

        # Ð“ÐµÐ½ÐµÑ€Ð¸Ñ€ÑƒÐµÐ¼ Ð¾Ñ‚Ñ‡ÐµÑ‚
        report = f"{'='*80}\n"
        report += f"  ÐžÐ¢Ð§Ð•Ð¢ ÐŸÐž Ð—ÐÐšÐÐ—ÐÐœ - {period.upper()}\n"
        report += f"  Ð¡Ð³ÐµÐ½ÐµÑ€Ð¸Ñ€Ð¾Ð²Ð°Ð½: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"{'='*80}\n\n"

        report += f"Ð’ÑÐµÐ³Ð¾ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²: {len(filtered_orders)}\n"
        report += f"Ð—Ð°Ð²ÐµÑ€ÑˆÐµÐ½Ð¾: {sum(1 for o in filtered_orders if o.get('status') == 'completed')}\n"
        report += f"Ð¡ Ð¾ÑˆÐ¸Ð±ÐºÐ°Ð¼Ð¸: {sum(1 for o in filtered_orders if 'error' in o.get('status', ''))}\n"
        report += f"Ð’ Ð¿Ñ€Ð¾Ñ†ÐµÑÑÐµ: {sum(1 for o in filtered_orders if o.get('status') not in ['completed', 'error', 'print_error'])}\n\n"

        report += f"{'='*80}\n"
        report += f"Ð”Ð•Ð¢ÐÐ›Ð˜ Ð—ÐÐšÐÐ—ÐžÐ’:\n"
        report += f"{'='*80}\n\n"

        for order in sorted(filtered_orders, key=lambda x: x.get('created_at', ''), reverse=True):
            report += f"Ð—Ð°ÐºÐ°Ð·: {order.get('order_id')}\n"
            report += f"  ÐšÐ»Ð¸ÐµÐ½Ñ‚: {order.get('customer', 'N/A')}\n"
            report += f"  Ð¡Ñ‚Ð°Ñ‚ÑƒÑ: {self.translate_status(order.get('status', ''))}\n"
            report += f"  Ð¡Ð¾Ð·Ð´Ð°Ð½: {order.get('created_at', 'N/A')}\n"
            report += f"  ÐÐ°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½: {'Ð”Ð°' if order.get('printed') else 'ÐÐµÑ‚'}\n"
            report += f"  Ð¡ÐºÐ»Ð°Ð´: {order.get('warehouse', 'N/A')}\n"
            report += f"{'-'*80}\n\n"

        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(1.0, report)

    def export_report(self):
        """Ð­ÐºÑÐ¿Ð¾Ñ€Ñ‚ Ð¾Ñ‚Ñ‡ÐµÑ‚Ð° Ð² Ñ„Ð°Ð¹Ð»"""
        from tkinter import filedialog

        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )

        if filename:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.report_text.get(1.0, tk.END))

            messagebox.showinfo("Ð£ÑÐ¿ÐµÑ…", f"ÐžÑ‚Ñ‡ÐµÑ‚ ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½:\n{filename}")
            self.log_message(f"ðŸ“¥ ÐžÑ‚Ñ‡ÐµÑ‚ ÑÐºÑÐ¿Ð¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½: {filename}", "success")

    async def websocket_handler(self):
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° WebSocket ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ñ"""
        while True:
            try:
                self.after(0, self.status_label.config, {'text': 'ðŸŸ¡ ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ...', 'foreground': 'orange'})
                self.after(0, self.log_message, "ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ Ðº ÑÐµÑ€Ð²ÐµÑ€Ñƒ...", "info")

                async with websockets.connect(SERVER_URL) as websocket:
                    self.ws = websocket
                    self.after(0, self.status_label.config, {'text': 'ðŸŸ¢ ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½', 'foreground': 'green'})
                    self.after(0, self.log_message, "âœ… ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¾ Ðº ÑÐµÑ€Ð²ÐµÑ€Ñƒ", "success")

                    async for message in websocket:
                        data = json.loads(message)
                        self.handle_message(data)

            except websockets.exceptions.WebSocketException as e:
                self.after(0, self.status_label.config, {'text': 'ðŸ”´ ÐžÑ‚ÐºÐ»ÑŽÑ‡ÐµÐ½', 'foreground': 'red'})
                self.after(0, self.log_message, f"âŒ Ð¡Ð¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ðµ Ð¿Ð¾Ñ‚ÐµÑ€ÑÐ½Ð¾: {e}", "error")
                await asyncio.sleep(5)
            except Exception as e:
                self.after(0, self.log_message, f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ°: {e}", "error")
                await asyncio.sleep(5)

    def handle_message(self, data):
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ð¹ Ð¾Ñ‚ ÑÐµÑ€Ð²ÐµÑ€Ð°"""
        msg_type = data.get('type')

        if msg_type == 'initial_state':
            orders = data.get('orders', {})
            stats = data.get('statistics', {})
            errors = data.get('errors', [])

            self.after(0, self.update_statistics, stats)

            for order_id, order_data in orders.items():
                self.after(0, self.update_order_in_tree, order_data)

            self.errors = errors
            self.after(0, self.refresh_errors)

            self.after(0, self.log_message, f"Ð—Ð°Ð³Ñ€ÑƒÐ¶ÐµÐ½Ð¾: {len(orders)} Ð·Ð°ÐºÐ°Ð·Ð¾Ð², {len(errors)} Ð¾ÑˆÐ¸Ð±Ð¾Ðº", "info")

        elif msg_type == 'order_update':
            order_id = data.get('order_id')
            update = data.get('update', {})

            if order_id and order_id in self.orders:
                existing_data = self.orders[order_id]['data']
                existing_data.update(update)
                existing_data['order_id'] = order_id

                self.after(0, self.update_order_in_tree, existing_data)

        elif msg_type == 'new_print_job':
            order = data.get('order', {})
            self.after(0, self.update_order_in_tree, order)
            self.after(0, self.log_message, f"ðŸ†• ÐÐ¾Ð²Ñ‹Ð¹ Ð·Ð°ÐºÐ°Ð·: {order.get('order_id')}", "info")

        elif msg_type == 'error':
            error = data.get('error', {})
            self.errors.insert(0, error)
            self.after(0, self.refresh_errors)
            self.after(0, self.log_message, f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ°: {error.get('order_id', 'N/A')}", "error")

        elif msg_type == 'statistics_update':
            stats = data.get('statistics', {})
            self.after(0, self.update_statistics, stats)

    async def send_to_server(self, data):
        """ÐžÑ‚Ð¿Ñ€Ð°Ð²ÐºÐ° Ð´Ð°Ð½Ð½Ñ‹Ñ… Ð½Ð° ÑÐµÑ€Ð²ÐµÑ€"""
        if self.ws:
            await self.ws.send(json.dumps(data))

    def run_websocket(self):
        """Ð—Ð°Ð¿ÑƒÑÐº WebSocket Ð² Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.ws_loop = loop
        loop.run_until_complete(self.websocket_handler())

    def on_closing(self):
        """Ð—Ð°ÐºÑ€Ñ‹Ñ‚Ð¸Ðµ Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ"""
        self.destroy()

# ============================================
# Ð—ÐÐŸÐ£Ð¡Ðš ÐŸÐ Ð˜Ð›ÐžÐ–Ð•ÐÐ˜Ð¯
# ============================================
if __name__ == "__main__":
    app = AdminPanel()
    app.mainloop()
