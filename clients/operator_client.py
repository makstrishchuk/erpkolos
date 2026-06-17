#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÐšÐ›Ð˜Ð•ÐÐ¢ Ð”Ð›Ð¯ ÐžÐŸÐ•Ð ÐÐ¢ÐžÐ Ð
Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ñ€Ð¾ÑÐ¼Ð¾Ñ‚Ñ€ ÑÑ‚Ð°Ñ‚ÑƒÑÐ° Ð·Ð°ÐºÐ°Ð·Ð¾Ð², Ð±ÐµÐ· Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑ‚Ð¸ ÑƒÐ¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ñ
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import asyncio
import websockets
import json
import threading
from datetime import datetime

# ============================================
# ÐÐÐ¡Ð¢Ð ÐžÐ™ÐšÐ˜
# ============================================
SERVER_URL = "ws://server01:8080/ws/operator"

# ============================================
# GUI Ð”Ð›Ð¯ ÐžÐŸÐ•Ð ÐÐ¢ÐžÐ Ð
# ============================================
class OperatorClient(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("ÐžÐŸÐ•Ð ÐÐ¢ÐžÐ  - ÐœÐ¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ Ð—Ð°ÐºÐ°Ð·Ð¾Ð²")
        self.geometry("1400x700")

        self.orders = {}
        self.statistics = {}
        self.ws = None

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

        ttk.Label(header, text="ðŸ‘ï¸ ÐŸÐÐÐ•Ð›Ð¬ ÐžÐŸÐ•Ð ÐÐ¢ÐžÐ Ð", font=("Arial", 16, "bold")).pack(side=tk.LEFT)

        self.status_label = ttk.Label(header, text="âšª ÐžÑ‚ÐºÐ»ÑŽÑ‡ÐµÐ½", font=("Arial", 10))
        self.status_label.pack(side=tk.RIGHT)

        # Ð¡Ñ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ°
        stats_frame = ttk.LabelFrame(self, text="ðŸ“Š Ð¡Ñ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ°")
        stats_frame.pack(fill=tk.X, padx=10, pady=5)

        self.stats_labels = {}
        stats_items = [
            ('total', 'Ð’ÑÐµÐ³Ð¾ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²'),
            ('successful', 'Ð£ÑÐ¿ÐµÑˆÐ½Ñ‹Ñ…'),
            ('failed', 'ÐžÑˆÐ¸Ð±Ð¾Ðº'),
            ('ftp_sent', 'ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¾ FTP')
        ]

        for i, (key, label) in enumerate(stats_items):
            ttk.Label(stats_frame, text=f"{label}:").grid(row=0, column=i*2, padx=5, pady=5, sticky=tk.W)
            self.stats_labels[key] = ttk.Label(stats_frame, text="0", font=("Arial", 12, "bold"))
            self.stats_labels[key].grid(row=0, column=i*2+1, padx=5, pady=5, sticky=tk.W)

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
        table_frame = ttk.LabelFrame(self, text="ðŸ“‹ Ð—Ð°ÐºÐ°Ð·Ñ‹")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ
        columns = ('order_id', 'customer', 'status', 'labels', 'invoice', 'ftp', 'time')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=15)

        # Ð—Ð°Ð³Ð¾Ð»Ð¾Ð²ÐºÐ¸
        self.tree.heading('order_id', text='ÐÐ¾Ð¼ÐµÑ€ Ð—Ð°ÐºÐ°Ð·Ð°')
        self.tree.heading('customer', text='ÐšÐ»Ð¸ÐµÐ½Ñ‚')
        self.tree.heading('status', text='Ð¡Ñ‚Ð°Ñ‚ÑƒÑ')
        self.tree.heading('labels', text='Ð­Ñ‚Ð¸ÐºÐµÑ‚ÐºÐ¸')
        self.tree.heading('invoice', text='Ð¡Ñ‡ÐµÑ‚')
        self.tree.heading('ftp', text='FTP')
        self.tree.heading('time', text='Ð’Ñ€ÐµÐ¼Ñ')

        # Ð¨Ð¸Ñ€Ð¸Ð½Ð° ÐºÐ¾Ð»Ð¾Ð½Ð¾Ðº
        self.tree.column('order_id', width=120, anchor=tk.CENTER)
        self.tree.column('customer', width=200)
        self.tree.column('status', width=150, anchor=tk.CENTER)
        self.tree.column('labels', width=180, anchor=tk.CENTER)
        self.tree.column('invoice', width=180, anchor=tk.CENTER)
        self.tree.column('ftp', width=100, anchor=tk.CENTER)
        self.tree.column('time', width=150, anchor=tk.CENTER)

        # Ð¡ÐºÑ€Ð¾Ð»Ð»Ð±Ð°Ñ€
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Ð¦Ð²ÐµÑ‚Ð¾Ð²Ñ‹Ðµ Ñ‚ÐµÐ³Ð¸
        self.tree.tag_configure('pending', background='#FFF9C4')  # Ð–ÐµÐ»Ñ‚Ñ‹Ð¹
        self.tree.tag_configure('processing', background='#B3E5FC')  # Ð“Ð¾Ð»ÑƒÐ±Ð¾Ð¹
        self.tree.tag_configure('completed', background='#C8E6C9')  # Ð—ÐµÐ»ÐµÐ½Ñ‹Ð¹
        self.tree.tag_configure('error', background='#FFCDD2')  # ÐšÑ€Ð°ÑÐ½Ñ‹Ð¹
        self.tree.tag_configure('printing', background='#E1BEE7')  # Ð¤Ð¸Ð¾Ð»ÐµÑ‚Ð¾Ð²Ñ‹Ð¹

        # Ð–ÑƒÑ€Ð½Ð°Ð» ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ð¹
        log_frame = ttk.LabelFrame(self, text="ðŸ“œ Ð–ÑƒÑ€Ð½Ð°Ð» Ð¡Ð¾Ð±Ñ‹Ñ‚Ð¸Ð¹")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Ð¢ÐµÐ³Ð¸ Ð´Ð»Ñ Ð»Ð¾Ð³Ð¾Ð²
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("info", foreground="blue")

    def log_message(self, message, tag="normal"):
        """Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ Ð² Ð»Ð¾Ð³"""
        self.log_text.configure(state='normal')
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')

    def update_statistics(self, stats):
        """ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ¸"""
        self.statistics = stats
        self.stats_labels['total'].config(text=str(stats.get('total_orders', 0)))
        self.stats_labels['successful'].config(text=str(stats.get('successful', 0)))
        self.stats_labels['failed'].config(text=str(stats.get('failed', 0)))
        self.stats_labels['ftp_sent'].config(text=str(stats.get('ftp_sent', 0)))

    def update_order(self, order_data):
        """ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ Ð¸Ð»Ð¸ Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ Ð·Ð°ÐºÐ°Ð·Ð° Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ"""
        order_id = order_data.get('order_id')

        # ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ Ñ‚ÐµÐ³ Ð´Ð»Ñ Ñ†Ð²ÐµÑ‚Ð°
        status = order_data.get('status', 'pending')
        tag = status

        # Ð¤Ð¾Ñ€Ð¼Ð°Ñ‚Ð¸Ñ€ÑƒÐµÐ¼ Ð²Ñ€ÐµÐ¼Ñ
        time_str = ''
        if 'created_at' in order_data:
            try:
                dt = datetime.fromisoformat(order_data['created_at'])
                time_str = dt.strftime('%H:%M:%S')
            except:
                time_str = 'N/A'

        # Ð”Ð°Ð½Ð½Ñ‹Ðµ Ð´Ð»Ñ ÑÑ‚Ñ€Ð¾ÐºÐ¸
        values = (
            order_id,
            order_data.get('customer', 'N/A'),
            self.translate_status(status),
            order_data.get('labels_status', 'â³'),
            order_data.get('invoice_status', 'N/A'),
            order_data.get('ftp_status', 'N/A'),
            time_str
        )

        # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ Ð¸Ð»Ð¸ ÑÐ¾Ð·Ð´Ð°ÐµÐ¼ ÑÑ‚Ñ€Ð¾ÐºÑƒ
        if order_id in self.orders:
            item_id = self.orders[order_id]['item_id']
            self.tree.item(item_id, values=values, tags=(tag,))
        else:
            item_id = self.tree.insert('', 0, values=values, tags=(tag,))
            self.orders[order_id] = {'item_id': item_id, 'data': order_data}

    def translate_status(self, status):
        """ÐŸÐµÑ€ÐµÐ²Ð¾Ð´ ÑÑ‚Ð°Ñ‚ÑƒÑÐ° Ð½Ð° Ñ€ÑƒÑÑÐºÐ¸Ð¹"""
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
            # ÐÐ°Ñ‡Ð°Ð»ÑŒÐ½Ð¾Ðµ ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ
            orders = data.get('orders', {})
            stats = data.get('statistics', {})

            self.after(0, self.update_statistics, stats)

            for order_id, order_data in orders.items():
                self.after(0, self.update_order, order_data)

            self.after(0, self.log_message, f"Ð—Ð°Ð³Ñ€ÑƒÐ¶ÐµÐ½Ð¾ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²: {len(orders)}", "info")

        elif msg_type == 'order_update':
            # ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ Ð·Ð°ÐºÐ°Ð·Ð°
            order_id = data.get('order_id')
            update = data.get('update', {})

            if order_id:
                self.after(0, self.update_order, update)
                self.after(0, self.log_message, f"ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½ Ð·Ð°ÐºÐ°Ð· {order_id}", "info")

        elif msg_type == 'new_print_job':
            # ÐÐ¾Ð²Ð¾Ðµ Ð·Ð°Ð´Ð°Ð½Ð¸Ðµ Ð½Ð° Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ
            order = data.get('order', {})
            order_id = order.get('order_id')

            self.after(0, self.update_order, order)
            self.after(0, self.log_message, f"ðŸ†• ÐÐ¾Ð²Ñ‹Ð¹ Ð·Ð°ÐºÐ°Ð·: {order_id}", "info")

        elif msg_type == 'error':
            # ÐžÑˆÐ¸Ð±ÐºÐ°
            error = data.get('error', {})
            order_id = error.get('order_id', 'unknown')
            error_msg = error.get('error', 'Unknown error')

            self.after(0, self.log_message, f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ° Ð² Ð·Ð°ÐºÐ°Ð·Ðµ {order_id}: {error_msg}", "error")

    def run_websocket(self):
        """Ð—Ð°Ð¿ÑƒÑÐº WebSocket Ð² Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.websocket_handler())

    def on_closing(self):
        """Ð—Ð°ÐºÑ€Ñ‹Ñ‚Ð¸Ðµ Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ"""
        self.destroy()

# ============================================
# Ð—ÐÐŸÐ£Ð¡Ðš
# ============================================
if __name__ == "__main__":
    app = OperatorClient()
    app.mainloop()
