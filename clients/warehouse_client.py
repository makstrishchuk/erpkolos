#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÐšÐ›Ð˜Ð•ÐÐ¢ Ð”Ð›Ð¯ Ð¡ÐšÐ›ÐÐ”Ð
- Ð’Ð¸Ð´Ð¸Ñ‚ Ð·Ð°Ð´Ð°Ð½Ð¸Ñ Ð½Ð° Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ
- Ð’Ð²Ð¾Ð´Ð¸Ñ‚ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº
- ÐŸÐµÑ‡Ð°Ñ‚Ð°ÐµÑ‚ ÑÑ‚Ð¸ÐºÐµÑ‚ÐºÐ¸ Ð½Ð° Ð»Ð¾ÐºÐ°Ð»ÑŒÐ½Ð¾Ð¼ Ð¿Ñ€Ð¸Ð½Ñ‚ÐµÑ€Ðµ
- ÐŸÐ¾Ð¸ÑÐº Ð¸ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ñ‹Ñ… ÑÑ‚Ð¸ÐºÐµÑ‚Ð¾Ðº
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, simpledialog, messagebox
import asyncio
import websockets
import json
import threading
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
import os
import socket

# ============================================
# ÐÐÐ¡Ð¢Ð ÐžÐ™ÐšÐ˜
# ============================================
SERVER_URL = "ws://server01:8080/ws/warehouse/{warehouse_id}"

CONFIG = {
    'GOLABEL': {
        'exe_path': r'C:\Program Files (x86)\GoDEX\GoLabel II\GoLabel.exe'
    },
    'PATHS': {
        'templates_folder': r'\\server01\data\maks\drucken\etiketten',
        'box_template_name': 'Box_Label.ezpx',
        'temp_folder': Path(os.getenv("TEMP")) / "WISO_Labels_Temp"
    }
}

# ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ ID ÑÐºÐ»Ð°Ð´Ð° Ð¸Ð· Ð¸Ð¼ÐµÐ½Ð¸ ÐºÐ¾Ð¼Ð¿ÑŒÑŽÑ‚ÐµÑ€Ð°
WAREHOUSE_ID = socket.gethostname()

# ============================================
# ÐŸÐ Ð˜ÐÐ¢Ð•Ð 
# ============================================
class LabelPrinter:
    def __init__(self):
        self.golabel_path = CONFIG['GOLABEL']['exe_path']
        self.templates_folder = Path(CONFIG['PATHS']['templates_folder'])
        self.box_template_path = self.templates_folder / CONFIG['PATHS']['box_template_name']
        self.temp_folder = CONFIG['PATHS']['temp_folder']
        self.temp_folder.mkdir(parents=True, exist_ok=True)

    def print_template(self, template_path, qty=1, data=None):
        """ÐŸÐµÑ‡Ð°Ñ‚ÑŒ ÑˆÐ°Ð±Ð»Ð¾Ð½Ð°"""
        local_path = self.temp_folder / template_path.name
        shutil.copy2(template_path, local_path)

        cmd = [self.golabel_path, '-f', str(local_path), '-c', str(qty)]

        data_path = None
        if data:
            data_path = self.temp_folder / "data.json"
            data_path.write_text(json.dumps(data, ensure_ascii=False), 'utf-8')
            cmd.extend(['-d', str(data_path)])

        try:
            subprocess.run(cmd, check=True, timeout=90, capture_output=True)
            return True
        except Exception as e:
            raise Exception(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿ÐµÑ‡Ð°Ñ‚Ð¸: {e}")
        finally:
            # Ð£Ð´Ð°Ð»ÑÐµÐ¼ Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½Ñ‹Ðµ Ñ„Ð°Ð¹Ð»Ñ‹
            local_path.unlink(missing_ok=True)
            if data_path:
                data_path.unlink(missing_ok=True)

    def clean_temp_folder(self):
        """ÐžÑ‡Ð¸ÑÑ‚ÐºÐ° Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½Ð¾Ð¹ Ð¿Ð°Ð¿ÐºÐ¸ Ð¾Ñ‚ Ð²ÑÐµÑ… Ñ„Ð°Ð¹Ð»Ð¾Ð²"""
        try:
            for file in self.temp_folder.glob('*'):
                if file.is_file():
                    file.unlink(missing_ok=True)
        except Exception as e:
            print(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ñ€Ð¸ Ð¾Ñ‡Ð¸ÑÑ‚ÐºÐµ temp Ð¿Ð°Ð¿ÐºÐ¸: {e}")

    def print_products(self, artikel_list):
        """ÐŸÐµÑ‡Ð°Ñ‚ÑŒ ÑÑ‚Ð¸ÐºÐµÑ‚Ð¾Ðº Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð²"""
        for artikel in artikel_list:
            pattern = f"{artikel['nummer']}_*"
            templates = list(self.templates_folder.glob(pattern))

            if not templates:
                raise FileNotFoundError(f"Ð¨Ð°Ð±Ð»Ð¾Ð½ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½ Ð´Ð»Ñ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð° {artikel['nummer']}")

            self.print_template(templates[0], qty=artikel['menge'])

    def print_box(self, kunde, address, box_num, total_boxes, lieferschein):
        """ÐŸÐµÑ‡Ð°Ñ‚ÑŒ ÑÑ‚Ð¸ÐºÐµÑ‚ÐºÐ¸ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ¸"""
        box_data = {
            'KUNDE': kunde,
            'ADRESSE': address,
            'BOX_NUM': f"{box_num} Ð¸Ð· {total_boxes}",
            'LIEFERSCHEIN': lieferschein
        }

        self.print_template(self.box_template_path, qty=1, data=box_data)

    def search_and_print(self, search_term, quantity=1):
        """ÐŸÐ¾Ð¸ÑÐº Ð¸ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ ÑÑ‚Ð¸ÐºÐµÑ‚ÐºÐ¸ Ð¿Ð¾ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñƒ"""
        pattern = f"{search_term}*"
        templates = list(self.templates_folder.glob(pattern))

        if not templates:
            raise FileNotFoundError(f"Ð¨Ð°Ð±Ð»Ð¾Ð½ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½ Ð´Ð»Ñ '{search_term}'")

        self.print_template(templates[0], qty=quantity)
        return templates[0].name

# ============================================
# GUI Ð”Ð›Ð¯ Ð¡ÐšÐ›ÐÐ”Ð
# ============================================
class WarehouseClient(tk.Tk):
    def __init__(self):
        print("="*60)
        print("âš ï¸  Ð—ÐÐŸÐ£Ð©Ð•Ð: clients/warehouse_client.py (GoLabel)")
        print("="*60)
        super().__init__()

        self.title(f"Ð¡ÐšÐ›ÐÐ” - {WAREHOUSE_ID}")
        self.geometry("1200x800")

        self.printer = LabelPrinter()
        self.pending_orders = {}
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

        ttk.Label(header, text=f"ðŸ“¦ Ð¡ÐšÐ›ÐÐ”: {WAREHOUSE_ID}", font=("Arial", 16, "bold")).pack(side=tk.LEFT)

        self.status_label = ttk.Label(header, text="âšª ÐžÑ‚ÐºÐ»ÑŽÑ‡ÐµÐ½", font=("Arial", 10))
        self.status_label.pack(side=tk.RIGHT)

        # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ notebook (Ð²ÐºÐ»Ð°Ð´ÐºÐ¸)
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Ð’ÐºÐ»Ð°Ð´ÐºÐ° 1: Ð—Ð°Ð´Ð°Ð½Ð¸Ñ Ð½Ð° Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ
        print_jobs_frame = ttk.Frame(notebook)
        notebook.add(print_jobs_frame, text="ðŸ–¨ï¸ Ð—Ð°Ð´Ð°Ð½Ð¸Ñ Ð½Ð° ÐŸÐµÑ‡Ð°Ñ‚ÑŒ")
        self.create_print_jobs_tab(print_jobs_frame)

        # Ð’ÐºÐ»Ð°Ð´ÐºÐ° 2: ÐŸÐ¾Ð¸ÑÐº Ð¸ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ
        search_frame = ttk.Frame(notebook)
        notebook.add(search_frame, text="ðŸ” ÐŸÐ¾Ð¸ÑÐº Ð¸ ÐŸÐµÑ‡Ð°Ñ‚ÑŒ")
        self.create_search_tab(search_frame)

        # Ð–ÑƒÑ€Ð½Ð°Ð»
        log_frame = ttk.LabelFrame(self, text="ðŸ“œ Ð–ÑƒÑ€Ð½Ð°Ð»")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, wrap=tk.WORD, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("info", foreground="blue")

    def create_print_jobs_tab(self, parent):
        """Ð’ÐºÐ»Ð°Ð´ÐºÐ° Ñ Ð·Ð°Ð´Ð°Ð½Ð¸ÑÐ¼Ð¸ Ð½Ð° Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ"""
        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
        columns = ('order_id', 'customer', 'artikel_count', 'status', 'action')
        self.jobs_tree = ttk.Treeview(parent, columns=columns, show='headings', height=15)

        self.jobs_tree.heading('order_id', text='ÐÐ¾Ð¼ÐµÑ€ Ð—Ð°ÐºÐ°Ð·Ð°')
        self.jobs_tree.heading('customer', text='ÐšÐ»Ð¸ÐµÐ½Ñ‚')
        self.jobs_tree.heading('artikel_count', text='ÐÑ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð²')
        self.jobs_tree.heading('status', text='Ð¡Ñ‚Ð°Ñ‚ÑƒÑ')
        self.jobs_tree.heading('action', text='Ð”ÐµÐ¹ÑÑ‚Ð²Ð¸Ðµ')

        self.jobs_tree.column('order_id', width=150, anchor=tk.CENTER)
        self.jobs_tree.column('customer', width=250)
        self.jobs_tree.column('artikel_count', width=100, anchor=tk.CENTER)
        self.jobs_tree.column('status', width=200, anchor=tk.CENTER)
        self.jobs_tree.column('action', width=150, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.jobs_tree.yview)
        self.jobs_tree.configure(yscroll=scrollbar.set)

        self.jobs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Ð¦Ð²ÐµÑ‚Ð¾Ð²Ñ‹Ðµ Ñ‚ÐµÐ³Ð¸
        self.jobs_tree.tag_configure('pending', background='#FFF9C4')
        self.jobs_tree.tag_configure('printing', background='#B3E5FC')
        self.jobs_tree.tag_configure('completed', background='#C8E6C9')

        # Ð”Ð²Ð¾Ð¹Ð½Ð¾Ð¹ ÐºÐ»Ð¸Ðº Ð´Ð»Ñ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸
        self.jobs_tree.bind('<Double-Button-1>', self.on_job_double_click)

        # ÐšÐ½Ð¾Ð¿ÐºÐ¸
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="ðŸ–¨ï¸ ÐŸÐµÑ‡Ð°Ñ‚ÑŒ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð½Ð¾Ð³Ð¾", command=self.print_selected_job).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="ðŸ”„ ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ", command=self.refresh_jobs).pack(side=tk.LEFT, padx=5)

    def create_search_tab(self, parent):
        """Ð’ÐºÐ»Ð°Ð´ÐºÐ° Ð¿Ð¾Ð¸ÑÐºÐ° Ð¸ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸"""
        # ÐŸÐ¾Ð¸ÑÐº
        search_frame = ttk.LabelFrame(parent, text="ðŸ” ÐŸÐ¾Ð¸ÑÐº Ð­Ñ‚Ð¸ÐºÐµÑ‚ÐºÐ¸")
        search_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(search_frame, text="ÐÑ€Ñ‚Ð¸ÐºÑƒÐ» Ð¸Ð»Ð¸ Ð½Ð°Ð·Ð²Ð°Ð½Ð¸Ðµ:").pack(side=tk.LEFT, padx=5)

        self.search_entry = ttk.Entry(search_frame, width=30)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind('<Return>', lambda e: self.search_labels())

        ttk.Button(search_frame, text="ðŸ” ÐÐ°Ð¹Ñ‚Ð¸", command=self.search_labels).pack(side=tk.LEFT, padx=5)

        # Ð ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ñ‹ Ð¿Ð¾Ð¸ÑÐºÐ°
        results_frame = ttk.LabelFrame(parent, text="ðŸ“‹ Ð ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ñ‹ ÐŸÐ¾Ð¸ÑÐºÐ°")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        columns = ('article', 'filename')
        self.search_tree = ttk.Treeview(results_frame, columns=columns, show='headings')

        self.search_tree.heading('article', text='ÐÑ€Ñ‚Ð¸ÐºÑƒÐ»')
        self.search_tree.heading('filename', text='Ð¤Ð°Ð¹Ð» Ð¨Ð°Ð±Ð»Ð¾Ð½Ð°')

        self.search_tree.column('article', width=150, anchor=tk.CENTER)
        self.search_tree.column('filename', width=400)

        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.search_tree.yview)
        self.search_tree.configure(yscroll=scrollbar.set)

        self.search_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ÐšÐ½Ð¾Ð¿ÐºÐ¸ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸
        print_frame = ttk.Frame(parent)
        print_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(print_frame, text="ÐšÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾:").pack(side=tk.LEFT, padx=5)

        self.qty_spinbox = ttk.Spinbox(print_frame, from_=1, to=100, width=10)
        self.qty_spinbox.set(1)
        self.qty_spinbox.pack(side=tk.LEFT, padx=5)

        ttk.Button(print_frame, text="ðŸ–¨ï¸ ÐŸÐµÑ‡Ð°Ñ‚ÑŒ Ð’Ñ‹Ð±Ñ€Ð°Ð½Ð½Ð¾Ð³Ð¾", command=self.print_selected_search_result).pack(side=tk.LEFT, padx=5)

    def log_message(self, message, tag="normal"):
        """Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ Ð² Ð»Ð¾Ð³"""
        self.log_text.configure(state='normal')
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state='disabled')

    def update_job_list(self, order):
        """ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐ¿Ð¸ÑÐºÐ° Ð·Ð°Ð´Ð°Ð½Ð¸Ð¹"""
        order_id = order.get('order_id')

        artikel_count = len(order.get('artikel', []))
        status = order.get('labels_status', 'â³ ÐžÐ¶Ð¸Ð´Ð°Ð½Ð¸Ðµ')

        values = (
            order_id,
            order.get('customer', 'N/A'),
            artikel_count,
            status,
            'â–¶ ÐŸÐµÑ‡Ð°Ñ‚ÑŒ'
        )

        # ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ Ñ‚ÐµÐ³
        if 'Ð“Ð¾Ñ‚Ð¾Ð²Ð¾' in status or 'âœ…' in status:
            tag = 'completed'
        elif 'ÐŸÐµÑ‡Ð°Ñ‚ÑŒ' in status:
            tag = 'printing'
        else:
            tag = 'pending'

        if order_id in self.pending_orders:
            item_id = self.pending_orders[order_id]['item_id']
            self.jobs_tree.item(item_id, values=values, tags=(tag,))
        else:
            item_id = self.jobs_tree.insert('', 'end', values=values, tags=(tag,))
            self.pending_orders[order_id] = {'item_id': item_id, 'data': order}

    def on_job_double_click(self, event):
        """Ð”Ð²Ð¾Ð¹Ð½Ð¾Ð¹ ÐºÐ»Ð¸Ðº Ð½Ð° Ð·Ð°Ð´Ð°Ð½Ð¸Ð¸"""
        self.print_selected_job()

    def print_selected_job(self):
        """ÐŸÐµÑ‡Ð°Ñ‚ÑŒ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð½Ð¾Ð³Ð¾ Ð·Ð°Ð´Ð°Ð½Ð¸Ñ"""
        selection = self.jobs_tree.selection()
        if not selection:
            messagebox.showwarning("ÐŸÑ€ÐµÐ´ÑƒÐ¿Ñ€ÐµÐ¶Ð´ÐµÐ½Ð¸Ðµ", "Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ Ð·Ð°Ð´Ð°Ð½Ð¸Ðµ Ð´Ð»Ñ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸")
            return

        item = selection[0]
        values = self.jobs_tree.item(item, 'values')
        order_id = values[0]

        if order_id not in self.pending_orders:
            messagebox.showerror("ÐžÑˆÐ¸Ð±ÐºÐ°", "Ð—Ð°Ð´Ð°Ð½Ð¸Ðµ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð¾")
            return

        order_data = self.pending_orders[order_id]['data']

        # Ð—Ð°Ð¿Ñ€Ð°ÑˆÐ¸Ð²Ð°ÐµÐ¼ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº
        box_count = simpledialog.askinteger(
            "ÐšÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº",
            f"Ð—Ð°ÐºÐ°Ð·: {order_id}\nÐšÐ»Ð¸ÐµÐ½Ñ‚: {order_data.get('customer')}\n\nÐ¡ÐºÐ¾Ð»ÑŒÐºÐ¾ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº?",
            minvalue=1,
            maxvalue=99,
            initialvalue=1
        )

        if not box_count:
            return

        # ÐŸÐµÑ‡Ð°Ñ‚Ð°ÐµÐ¼ Ð² Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ
        threading.Thread(target=self.process_print_job, args=(order_data, box_count), daemon=True).start()

    def auto_print_job(self, order_data):
        """ÐÐ’Ð¢ÐžÐœÐÐ¢Ð˜Ð§Ð•Ð¡ÐšÐÐ¯ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð² Ð¿Ñ€Ð¸ Ð¿Ð¾Ð»ÑƒÑ‡ÐµÐ½Ð¸Ð¸ Ð½Ð¾Ð²Ð¾Ð³Ð¾ Ð·Ð°Ð´Ð°Ð½Ð¸Ñ"""
        order_id = order_data.get('order_id')

        # Ð—Ð°Ð¿ÑƒÑÐºÐ°ÐµÐ¼ Ð² Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ
        threading.Thread(target=self._auto_print_products, args=(order_data,), daemon=True).start()

    def _auto_print_products(self, order_data):
        """ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ°Ñ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð² Ð² Ñ„Ð¾Ð½Ð¾Ð²Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ"""
        order_id = order_data.get('order_id')

        try:
            self.after(0, self.log_message, f"ðŸ–¨ï¸ ÐÐ’Ð¢ÐžÐœÐÐ¢Ð˜Ð§Ð•Ð¡ÐšÐÐ¯ ÐŸÐ•Ð§ÐÐ¢Ð¬ Ð·Ð°ÐºÐ°Ð·Ð° {order_id}", "info")

            # ÐŸÐµÑ‡Ð°Ñ‚Ð°ÐµÐ¼ Ñ‚Ð¾Ð²Ð°Ñ€Ñ‹
            artikel_list = order_data.get('artikel', [])
            self.after(0, self.log_message, f"ÐŸÐµÑ‡Ð°Ñ‚ÑŒ {len(artikel_list)} Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð²...", "info")
            self.printer.print_products(artikel_list)

            self.after(0, self.log_message, f"âœ… Ð¢Ð¾Ð²Ð°Ñ€Ñ‹ Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½Ñ‹!", "success")

            # Ð¢Ð•ÐŸÐ•Ð Ð¬ ÑÐ¿Ñ€Ð°ÑˆÐ¸Ð²Ð°ÐµÐ¼ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº
            self.after(0, self._ask_box_count, order_data)

        except Exception as e:
            error_msg = str(e)
            self.after(0, self.log_message, f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð²: {error_msg}", "error")
            self.after(0, messagebox.showerror, "ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿ÐµÑ‡Ð°Ñ‚Ð¸", f"ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ñ‚ÑŒ Ñ‚Ð¾Ð²Ð°Ñ€Ñ‹:\n{error_msg}")

            # Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ ÑÐµÑ€Ð²ÐµÑ€ Ð¾Ð± Ð¾ÑˆÐ¸Ð±ÐºÐµ
            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_server({
                        'type': 'print_complete',
                        'order_id': order_id,
                        'success': False,
                        'error': error_msg
                    }),
                    self.ws_loop
                )

    def _ask_box_count(self, order_data):
        """Ð—Ð°Ð¿Ñ€Ð¾Ñ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð° ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº ÐŸÐžÐ¡Ð›Ð• Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð²"""
        order_id = order_data.get('order_id')

        box_count = simpledialog.askinteger(
            "ÐšÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº",
            f"âœ… Ð¢Ð¾Ð²Ð°Ñ€Ñ‹ Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½Ñ‹!\n\nÐ—Ð°ÐºÐ°Ð·: {order_id}\nÐšÐ»Ð¸ÐµÐ½Ñ‚: {order_data.get('customer')}\n\nÐ¡ÐºÐ¾Ð»ÑŒÐºÐ¾ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ñ‚ÑŒ?",
            minvalue=1,
            maxvalue=99,
            initialvalue=1
        )

        if not box_count:
            self.log_message(f"âš ï¸ ÐŸÐµÑ‡Ð°Ñ‚ÑŒ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº Ð¾Ñ‚Ð¼ÐµÐ½ÐµÐ½Ð° Ð´Ð»Ñ Ð·Ð°ÐºÐ°Ð·Ð° {order_id}", "error")
            return

        # ÐŸÐµÑ‡Ð°Ñ‚Ð°ÐµÐ¼ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ¸ Ð² Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ
        threading.Thread(target=self._print_boxes, args=(order_data, box_count), daemon=True).start()

    def _print_boxes(self, order_data, box_count):
        """ÐŸÐµÑ‡Ð°Ñ‚ÑŒ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº Ð² Ñ„Ð¾Ð½Ð¾Ð²Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ"""
        order_id = order_data.get('order_id')

        try:
            self.after(0, self.log_message, f"ðŸ–¨ï¸ ÐŸÐµÑ‡Ð°Ñ‚ÑŒ {box_count} ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº...", "info")

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº Ð½Ð° ÑÐµÑ€Ð²ÐµÑ€
            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_server({
                        'type': 'box_count',
                        'order_id': order_id,
                        'box_count': box_count
                    }),
                    self.ws_loop
                )

            # ÐŸÐµÑ‡Ð°Ñ‚Ð°ÐµÐ¼ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ¸
            for i in range(1, box_count + 1):
                self.after(0, self.log_message, f"ÐŸÐµÑ‡Ð°Ñ‚ÑŒ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ¸ {i}/{box_count}...", "info")
                self.printer.print_box(
                    order_data.get('customer', ''),
                    order_data.get('address', ''),
                    i,
                    box_count,
                    order_id
                )

            # ÐžÑ‡Ð¸Ñ‰Ð°ÐµÐ¼ Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½ÑƒÑŽ Ð¿Ð°Ð¿ÐºÑƒ Ð¿Ð¾ÑÐ»Ðµ ÑƒÑÐ¿ÐµÑˆÐ½Ð¾Ð¹ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸
            self.printer.clean_temp_folder()

            # Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ ÑÐµÑ€Ð²ÐµÑ€ Ð¾Ð± ÑƒÑÐ¿ÐµÑ…Ðµ
            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_server({
                        'type': 'print_complete',
                        'order_id': order_id,
                        'success': True
                    }),
                    self.ws_loop
                )

            self.after(0, self.log_message, f"âœ… Ð—Ð°ÐºÐ°Ð· {order_id} ÐŸÐžÐ›ÐÐžÐ¡Ð¢Ð¬Ð® Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½! Temp Ð¿Ð°Ð¿ÐºÐ° Ð¾Ñ‡Ð¸Ñ‰ÐµÐ½Ð°.", "success")
            self.after(0, messagebox.showinfo, "Ð£ÑÐ¿ÐµÑ…", f"Ð—Ð°ÐºÐ°Ð· {order_id} Ð¿Ð¾Ð»Ð½Ð¾ÑÑ‚ÑŒÑŽ Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½!\n\nÐ¢Ð¾Ð²Ð°Ñ€Ñ‹: {len(order_data.get('artikel', []))} ÑˆÑ‚.\nÐšÐ¾Ñ€Ð¾Ð±ÐºÐ¸: {box_count} ÑˆÑ‚.")

        except Exception as e:
            error_msg = str(e)
            self.after(0, self.log_message, f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº: {error_msg}", "error")
            self.after(0, messagebox.showerror, "ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿ÐµÑ‡Ð°Ñ‚Ð¸", f"ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ñ‚ÑŒ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ¸:\n{error_msg}")

            # Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ ÑÐµÑ€Ð²ÐµÑ€ Ð¾Ð± Ð¾ÑˆÐ¸Ð±ÐºÐµ
            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_server({
                        'type': 'print_complete',
                        'order_id': order_id,
                        'success': False,
                        'error': error_msg
                    }),
                    self.ws_loop
                )

    def process_print_job(self, order_data, box_count):
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ Ð·Ð°Ð´Ð°Ð½Ð¸Ñ (Ð Ð£Ð§ÐÐžÐ™ Ð—ÐÐŸÐ£Ð¡Ðš Ð¸Ð· Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹)"""
        order_id = order_data.get('order_id')

        try:
            self.after(0, self.log_message, f"ðŸ–¨ï¸ ÐÐ°Ñ‡Ð°Ð»Ð¾ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ Ð·Ð°ÐºÐ°Ð·Ð° {order_id}", "info")

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº Ð½Ð° ÑÐµÑ€Ð²ÐµÑ€
            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_server({
                        'type': 'box_count',
                        'order_id': order_id,
                        'box_count': box_count
                    }),
                    self.ws_loop
                )

            # ÐŸÐµÑ‡Ð°Ñ‚Ð°ÐµÐ¼ Ñ‚Ð¾Ð²Ð°Ñ€Ñ‹
            self.after(0, self.log_message, f"ÐŸÐµÑ‡Ð°Ñ‚ÑŒ Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð²...", "info")
            self.printer.print_products(order_data.get('artikel', []))

            # ÐŸÐµÑ‡Ð°Ñ‚Ð°ÐµÐ¼ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ¸
            self.after(0, self.log_message, f"ÐŸÐµÑ‡Ð°Ñ‚ÑŒ {box_count} ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº...", "info")
            for i in range(1, box_count + 1):
                self.printer.print_box(
                    order_data.get('customer', ''),
                    order_data.get('address', ''),
                    i,
                    box_count,
                    order_id
                )

            # Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ ÑÐµÑ€Ð²ÐµÑ€ Ð¾Ð± ÑƒÑÐ¿ÐµÑ…Ðµ
            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_server({
                        'type': 'print_complete',
                        'order_id': order_id,
                        'success': True
                    }),
                    self.ws_loop
                )

            self.after(0, self.log_message, f"âœ… Ð—Ð°ÐºÐ°Ð· {order_id} Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½ ÑƒÑÐ¿ÐµÑˆÐ½Ð¾", "success")
            self.after(0, messagebox.showinfo, "Ð£ÑÐ¿ÐµÑ…", f"Ð—Ð°ÐºÐ°Ð· {order_id} Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½!\n{box_count} ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº")

        except Exception as e:
            error_msg = str(e)
            self.after(0, self.log_message, f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿ÐµÑ‡Ð°Ñ‚Ð¸: {error_msg}", "error")
            self.after(0, messagebox.showerror, "ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿ÐµÑ‡Ð°Ñ‚Ð¸", error_msg)

            # Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ ÑÐµÑ€Ð²ÐµÑ€ Ð¾Ð± Ð¾ÑˆÐ¸Ð±ÐºÐµ
            if self.ws:
                asyncio.run_coroutine_threadsafe(
                    self.send_to_server({
                        'type': 'print_complete',
                        'order_id': order_id,
                        'success': False,
                        'error': error_msg
                    }),
                    self.ws_loop
                )

    def search_labels(self):
        """ÐŸÐ¾Ð¸ÑÐº ÑÑ‚Ð¸ÐºÐµÑ‚Ð¾Ðº"""
        search_term = self.search_entry.get().strip()

        if not search_term:
            messagebox.showwarning("ÐŸÑ€ÐµÐ´ÑƒÐ¿Ñ€ÐµÐ¶Ð´ÐµÐ½Ð¸Ðµ", "Ð’Ð²ÐµÐ´Ð¸Ñ‚Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» Ð´Ð»Ñ Ð¿Ð¾Ð¸ÑÐºÐ°")
            return

        # ÐžÑ‡Ð¸Ñ‰Ð°ÐµÐ¼ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ñ‹
        for item in self.search_tree.get_children():
            self.search_tree.delete(item)

        try:
            templates_path = Path(CONFIG['PATHS']['templates_folder'])
            pattern = f"{search_term}*"
            results = list(templates_path.glob(pattern))

            if not results:
                self.log_message(f"âŒ ÐÐµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð¾ ÑÑ‚Ð¸ÐºÐµÑ‚Ð¾Ðº Ð´Ð»Ñ '{search_term}'", "error")
                messagebox.showinfo("ÐŸÐ¾Ð¸ÑÐº", f"Ð­Ñ‚Ð¸ÐºÐµÑ‚ÐºÐ¸ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ñ‹ Ð´Ð»Ñ '{search_term}'")
                return

            for file in results:
                article = file.stem.split('_')[0] if '_' in file.name else file.stem
                self.search_tree.insert('', 'end', values=(article, file.name))

            self.log_message(f"âœ… ÐÐ°Ð¹Ð´ÐµÐ½Ð¾ ÑÑ‚Ð¸ÐºÐµÑ‚Ð¾Ðº: {len(results)}", "success")

        except Exception as e:
            self.log_message(f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ð¾Ð¸ÑÐºÐ°: {e}", "error")
            messagebox.showerror("ÐžÑˆÐ¸Ð±ÐºÐ°", f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ð¾Ð¸ÑÐºÐ°: {e}")

    def print_selected_search_result(self):
        """ÐŸÐµÑ‡Ð°Ñ‚ÑŒ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð½Ð¾Ð³Ð¾ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ð° Ð¿Ð¾Ð¸ÑÐºÐ°"""
        selection = self.search_tree.selection()
        if not selection:
            messagebox.showwarning("ÐŸÑ€ÐµÐ´ÑƒÐ¿Ñ€ÐµÐ¶Ð´ÐµÐ½Ð¸Ðµ", "Ð’Ñ‹Ð±ÐµÑ€Ð¸Ñ‚Ðµ ÑÑ‚Ð¸ÐºÐµÑ‚ÐºÑƒ Ð´Ð»Ñ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸")
            return

        item = selection[0]
        values = self.search_tree.item(item, 'values')
        article = values[0]

        try:
            qty = int(self.qty_spinbox.get())
            filename = self.printer.search_and_print(article, qty)
            self.log_message(f"âœ… ÐÐ°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½Ð¾ {qty} ÑˆÑ‚. '{filename}'", "success")
            messagebox.showinfo("Ð£ÑÐ¿ÐµÑ…", f"ÐÐ°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½Ð¾ {qty} ÑÑ‚Ð¸ÐºÐµÑ‚Ð¾Ðº")
        except Exception as e:
            self.log_message(f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿ÐµÑ‡Ð°Ñ‚Ð¸: {e}", "error")
            messagebox.showerror("ÐžÑˆÐ¸Ð±ÐºÐ°", str(e))

    def refresh_jobs(self):
        """ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐ¿Ð¸ÑÐºÐ° Ð·Ð°Ð´Ð°Ð½Ð¸Ð¹"""
        self.log_message("ðŸ”„ ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÐ¿Ð¸ÑÐºÐ° Ð·Ð°Ð´Ð°Ð½Ð¸Ð¹...", "info")

    async def send_to_server(self, data):
        """ÐžÑ‚Ð¿Ñ€Ð°Ð²ÐºÐ° Ð´Ð°Ð½Ð½Ñ‹Ñ… Ð½Ð° ÑÐµÑ€Ð²ÐµÑ€"""
        if self.ws:
            await self.ws.send(json.dumps(data))

    async def websocket_handler(self):
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° WebSocket ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ñ"""
        url = SERVER_URL.format(warehouse_id=WAREHOUSE_ID)

        while True:
            try:
                self.after(0, self.status_label.config, {'text': 'ðŸŸ¡ ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ...', 'foreground': 'orange'})
                self.after(0, self.log_message, "ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ Ðº ÑÐµÑ€Ð²ÐµÑ€Ñƒ...", "info")

                async with websockets.connect(url) as websocket:
                    self.ws = websocket
                    self.after(0, self.status_label.config, {'text': 'ðŸŸ¢ ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½', 'foreground': 'green'})
                    self.after(0, self.log_message, "âœ… ÐŸÐ¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¾ Ðº ÑÐµÑ€Ð²ÐµÑ€Ñƒ", "success")

                    async for message in websocket:
                        data = json.loads(message)
                        self.handle_message(data)

            except websockets.exceptions.WebSocketException as e:
                self.ws = None
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
            pending_prints = data.get('pending_prints', [])
            for order in pending_prints:
                self.after(0, self.update_job_list, order)

        elif msg_type == 'new_print_job':
            order = data.get('order', {})
            self.after(0, self.update_job_list, order)
            self.after(0, self.log_message, f"ðŸ†• ÐÐ¾Ð²Ð¾Ðµ Ð·Ð°Ð´Ð°Ð½Ð¸Ðµ: {order.get('order_id')}", "info")

            # ÐÐ’Ð¢ÐžÐœÐÐ¢Ð˜Ð§Ð•Ð¡ÐšÐ˜ Ð½Ð°Ñ‡Ð¸Ð½Ð°ÐµÐ¼ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð²
            self.after(0, self.auto_print_job, order)

        elif msg_type == 'order_update':
            order_id = data.get('order_id')
            update = data.get('update', {})

            if order_id in self.pending_orders:
                self.pending_orders[order_id]['data'].update(update)
                self.after(0, self.update_job_list, self.pending_orders[order_id]['data'])

    def run_websocket(self):
        """Ð—Ð°Ð¿ÑƒÑÐº WebSocket Ð² Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ"""
        self.ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.ws_loop)
        self.ws_loop.run_until_complete(self.websocket_handler())

    def on_closing(self):
        """Ð—Ð°ÐºÑ€Ñ‹Ñ‚Ð¸Ðµ Ð¿Ñ€Ð¸Ð»Ð¾Ð¶ÐµÐ½Ð¸Ñ"""
        self.destroy()

# ============================================
# Ð—ÐÐŸÐ£Ð¡Ðš
# ============================================
if __name__ == "__main__":
    app = WarehouseClient()
    app.mainloop()
