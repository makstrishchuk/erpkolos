import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import logging
import time
import queue
from datetime import datetime

# Подключаем графики
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.pyplot as plt
except ImportError:
    messagebox.showerror("Ошибка", "Не установлен matplotlib.\nВыполните: pip install matplotlib")
    raise

# --- ПАЛИТРА "SOFT IOS" ---
COLORS = {
    "bg": "#EEF3FB",
    "card": "#FFFFFF",
    "header_text": "#0F172A",
    "sub_text": "#64748B",
    "blue_card": "#0A84FF",
    "orange_card": "#F59E0B",
    "teal_card": "#22C55E",
    "purple_card": "#7C3AED",
    "purple_chart": "#6366F1",
    "success": "#22C55E",
    "danger": "#EF4444",
    "table_header": "#E8F1FF",
    "table_row": "#FFFFFF",
    "table_row_alt": "#F8FBFF",
    "select": "#0A84FF",
    "log_bg": "#0B1220",
    "log_fg": "#CDE9FF",
    "border": "#DCE6F5"
}

class ThreadSafeLogHandler(logging.Handler):
    """Безопасный обработчик логов"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

class ServerGUI(tk.Tk):
    def __init__(self, server_instance, title="WISO GoLabel Server"):
        super().__init__()
        self.server = server_instance
        self.title(title)
        self.geometry("1300x850")
        self.configure(bg=COLORS["bg"])
        
        self.log_queue = queue.Queue()
        
        self.setup_styles()
        self.create_layout()
        
        self.start_time = time.time()
        
        # Запуск циклов
        self.check_log_queue()
        self.update_dashboard_loop()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Основной фон
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Card.TFrame", background=COLORS["card"])
        
        # Лейблы (используем ttk для стилизации)
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["header_text"], font=("Segoe UI", 10))
        
        # Специальные стили для карточек (ИСПРАВЛЕНО)
        style.configure("Card.TLabel", background=COLORS["card"], foreground=COLORS["sub_text"], font=("Segoe UI", 10))
        style.configure("CardValue.TLabel", background=COLORS["card"], foreground=COLORS["header_text"], font=("Segoe UI", 28, "bold"))
        
        # Вкладки
        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=COLORS["card"], 
                        foreground=COLORS["sub_text"], 
                        padding=[22, 11],
                        font=("Segoe UI", 10, "bold"),
                        borderwidth=0)
        style.map("TNotebook.Tab", 
                  background=[("selected", COLORS["blue_card"])], 
                  foreground=[("selected", "#FFFFFF")])

        # Таблицы
        style.configure("Treeview",
                        background=COLORS["table_row"],
                        foreground=COLORS["header_text"],
                        fieldbackground=COLORS["table_row"],
                        borderwidth=0,
                        rowheight=36,
                        font=("Segoe UI", 10))

        style.configure("Treeview.Heading",
                        background=COLORS["table_header"],
                        foreground=COLORS["sub_text"],
                        relief="flat",
                        padding=(10, 10),
                        font=("Segoe UI", 9, "bold"))

        style.map("Treeview", background=[("selected", COLORS["select"])], foreground=[("selected", "#FFFFFF")])

        # Кнопки
        style.configure("TButton",
                        background=COLORS["card"],
                        foreground=COLORS["header_text"],
                        borderwidth=0,
                        font=("Segoe UI", 10, "bold"),
                        padding=(14, 9))
        style.map("TButton", background=[("active", "#E8F1FF")])

        style.configure("Action.TButton", background=COLORS["blue_card"], foreground="white")
        style.configure("Danger.TButton", background=COLORS["danger"], foreground="white")

    def create_layout(self):
        # --- HEADER ---
        header = tk.Frame(self, bg=COLORS["bg"], height=60)
        header.pack(fill=tk.X, padx=30, pady=(20, 10))
        
        logo = tk.Label(header, text="WISO GO LABEL", bg=COLORS["bg"], fg=COLORS["blue_card"], font=("Segoe UI", 22, "bold"))
        logo.pack(side=tk.LEFT)
        
        # Статус
        status_frame = tk.Frame(header, bg=COLORS["bg"])
        status_frame.pack(side=tk.RIGHT)
        
        self.status_lbl = tk.Label(status_frame, text="ONLINE", bg=COLORS["bg"], fg=COLORS["success"], font=("Segoe UI", 10, "bold"))
        self.status_lbl.pack(side=tk.RIGHT, padx=10)
        
        tk.Label(status_frame, text="Server Status:", bg=COLORS["bg"], fg=COLORS["sub_text"]).pack(side=tk.RIGHT)

        # --- TABS ---
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=30, pady=10)
        
        dash = ttk.Frame(self.notebook); self.notebook.add(dash, text="  ГЛАВНАЯ  ")
        self.create_dashboard_tab(dash)
        
        logs = ttk.Frame(self.notebook); self.notebook.add(logs, text="  ЛОГИ  ")
        self.create_logs_tab(logs)
        
        users = ttk.Frame(self.notebook); self.notebook.add(users, text="  СЕССИИ  ")
        self.create_users_tab(users)
        
        ctrl = ttk.Frame(self.notebook); self.notebook.add(ctrl, text="  УПРАВЛЕНИЕ  ")
        self.create_control_tab(ctrl)

    # ==========================================
    # DASHBOARD
    # ==========================================
    def create_dashboard_tab(self, parent):
        self.kpi_labels = {}
        self.dashboard_period = tk.StringVar(value="today")

        # --- FILTER ROW (Период) ---
        filter_frame = tk.Frame(parent, bg=COLORS["bg"])
        filter_frame.pack(fill=tk.X, pady=(10, 5), padx=10)

        tk.Label(filter_frame, text="Период:", bg=COLORS["bg"], fg=COLORS["sub_text"],
                 font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 10))

        periods = [("Сегодня", "today"), ("3 дня", "3days"), ("Неделя", "week"), ("Месяц", "month"), ("Всё", "all")]
        for text, value in periods:
            rb = tk.Radiobutton(filter_frame, text=text, variable=self.dashboard_period, value=value,
                                bg=COLORS["bg"], fg=COLORS["header_text"], selectcolor=COLORS["card"],
                                activebackground=COLORS["bg"], activeforeground=COLORS["blue_card"],
                                font=("Segoe UI", 9), command=self.update_dashboard_now)
            rb.pack(side=tk.LEFT, padx=5)

        # Время работы справа
        self.uptime_label = tk.Label(filter_frame, text="⏱ 00:00:00", bg=COLORS["bg"],
                                     fg=COLORS["teal_card"], font=("Segoe UI", 10, "bold"))
        self.uptime_label.pack(side=tk.RIGHT, padx=10)

        # --- KPI CARDS ROW 1: Основная статистика ---
        kpi_container1 = tk.Frame(parent, bg=COLORS["bg"])
        kpi_container1.pack(fill=tk.X, pady=(10, 5), padx=10)

        self.create_kpi_card(kpi_container1, "ОНЛАЙН", "active", COLORS["purple_card"], "0")
        self.create_kpi_card(kpi_container1, "СОБРАНО ✓", "completed", COLORS["teal_card"], "0")
        self.create_kpi_card(kpi_container1, "В РАБОТЕ", "in_progress", COLORS["orange_card"], "0")
        self.create_kpi_card(kpi_container1, "НЕ НАЧАТО", "not_started", COLORS["danger"], "0")

        # --- KPI CARDS ROW 2: Дополнительная статистика ---
        kpi_container2 = tk.Frame(parent, bg=COLORS["bg"])
        kpi_container2.pack(fill=tk.X, pady=(5, 10), padx=10)

        self.create_kpi_card(kpi_container2, "ВСЕГО ЗАКАЗОВ", "orders_total", COLORS["blue_card"], "0")
        self.create_kpi_card(kpi_container2, "НАПЕЧАТАНО", "printed", COLORS["purple_chart"], "0")
        self.create_kpi_card(kpi_container2, "СО СЧЕТАМИ", "with_invoice", COLORS["teal_card"], "0")
        self.create_kpi_card(kpi_container2, "ПОЗИЦИЙ", "total_items", COLORS["orange_card"], "0")

        # --- CHARTS ROW ---
        chart_container = tk.Frame(parent, bg=COLORS["bg"])
        chart_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Левый график (Статус сборки - Donut)
        left_frame = tk.Frame(chart_container, bg=COLORS["card"], padx=20, pady=15)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        tk.Label(left_frame, text="Статус сборки", bg=COLORS["card"], fg=COLORS["header_text"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")

        self.fig_pie = Figure(figsize=(4, 3), dpi=100, facecolor=COLORS["card"])
        self.ax_pie = self.fig_pie.add_subplot(111)
        self.fig_pie.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.05)
        self.canvas_pie = FigureCanvasTkAgg(self.fig_pie, master=left_frame)
        self.canvas_pie.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Легенда под графиком
        self.pie_legend = tk.Label(left_frame, text="", bg=COLORS["card"], fg=COLORS["sub_text"],
                                   font=("Segoe UI", 9))
        self.pie_legend.pack(anchor="w", pady=(5, 0))

        # Правый график (По маршрутам - Bar)
        right_frame = tk.Frame(chart_container, bg=COLORS["card"], padx=20, pady=15)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        tk.Label(right_frame, text="Заказы по маршрутам", bg=COLORS["card"], fg=COLORS["header_text"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")

        self.fig_bar = Figure(figsize=(4, 3), dpi=100, facecolor=COLORS["card"])
        self.ax_bar = self.fig_bar.add_subplot(111)
        self.ax_bar.set_facecolor(COLORS["card"])
        self.fig_bar.subplots_adjust(left=0.15, right=0.95, top=0.9, bottom=0.2)
        self.canvas_bar = FigureCanvasTkAgg(self.fig_bar, master=right_frame)
        self.canvas_bar.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def create_kpi_card(self, parent, title, key, color, default_val):
        # Фрейм карточки (уменьшенная высота для 2 рядов)
        card = tk.Frame(parent, bg=COLORS["card"], height=80)
        card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        card.pack_propagate(False)

        # Полоса
        strip = tk.Frame(card, bg=color, width=4)
        strip.pack(side=tk.LEFT, fill=tk.Y)

        # Контент
        content = tk.Frame(card, bg=COLORS["card"], padx=15)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Заголовок (мельче)
        tk.Label(content, text=title, bg=COLORS["card"], fg=COLORS["sub_text"],
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(10, 2))

        # Значение (крупное)
        lbl = tk.Label(content, text=default_val, bg=COLORS["card"], fg=COLORS["header_text"],
                       font=("Segoe UI", 20, "bold"))
        lbl.pack(anchor="w")

        self.kpi_labels[key] = lbl

    # ==========================================
    # LOGIC
    # ==========================================
    def update_dashboard_now(self):
        """Принудительное обновление дашборда при смене периода"""
        self.update_dashboard_stats()

    def get_period_filter(self):
        """Получить SQL условие для фильтра по периоду"""
        period = self.dashboard_period.get()
        if period == "today":
            return "date(json_extract(order_data, '$.date')) = date('now')"
        elif period == "3days":
            return "date(json_extract(order_data, '$.date')) >= date('now', '-3 days')"
        elif period == "week":
            return "date(json_extract(order_data, '$.date')) >= date('now', '-7 days')"
        elif period == "month":
            return "date(json_extract(order_data, '$.date')) >= date('now', '-30 days')"
        else:  # all
            return "1=1"

    def update_dashboard_loop(self):
        """Цикл обновления данных (каждые 3 секунды)"""
        self.after(3000, self.update_dashboard_loop)
        self.update_dashboard_stats()

    def update_dashboard_stats(self):
        """Обновление статистики дашборда"""
        try:
            # 1. Uptime
            if hasattr(self, 'start_time') and hasattr(self, 'uptime_label'):
                elapsed = int(time.time() - self.start_time)
                uptime_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
                self.uptime_label.config(text=f"⏱ {uptime_str}")

            # 2. Users (Активные сессии)
            if hasattr(self.server, 'sessions'):
                current_sessions = self.server.sessions.sessions
                if 'active' in self.kpi_labels:
                    self.kpi_labels['active'].config(text=str(len(current_sessions)))
                self.update_users_table(current_sessions)

            # 3. SQL Stats (Заказы)
            if hasattr(self.server, 'db'):
                import json as json_lib
                conn = self.server.db.get_connection()
                cur = conn.cursor()

                period_filter = self.get_period_filter()

                # Получаем все заказы за период
                cur.execute(f"SELECT order_id, order_data, printed FROM orders WHERE {period_filter}")
                orders = cur.fetchall()

                total = len(orders)
                completed = 0  # Полностью собрано
                in_progress = 0  # Частично собрано
                not_started = 0  # Не начато
                printed = 0  # Этикетки напечатаны
                with_invoice = 0  # Со счетами
                total_items = 0  # Всего позиций
                routes_count = {}  # По маршрутам

                for order_id, order_data_str, is_printed in orders:
                    try:
                        order_data = json_lib.loads(order_data_str)
                    except:
                        continue

                    # Считаем позиции и статус сборки
                    artikel = order_data.get('artikel', [])
                    total_items += len(artikel)

                    picked_count = 0
                    total_count = len(artikel)
                    for art in artikel:
                        if art.get('picked', False):
                            picked_count += 1

                    # Определяем статус сборки
                    if total_count > 0:
                        if picked_count == total_count:
                            completed += 1
                        elif picked_count > 0:
                            in_progress += 1
                        else:
                            not_started += 1
                    else:
                        not_started += 1

                    # Напечатано
                    if is_printed:
                        printed += 1

                    # Со счетами
                    invoice_status = order_data.get('invoice_status', '')
                    if invoice_status and '✅' in invoice_status:
                        with_invoice += 1

                    # По маршрутам
                    route = order_data.get('route_name', order_data.get('route', 'Без маршрута'))
                    if not route:
                        route = 'Без маршрута'
                    routes_count[route] = routes_count.get(route, 0) + 1

                conn.close()

                # Обновляем KPI карточки
                if 'orders_total' in self.kpi_labels:
                    self.kpi_labels['orders_total'].config(text=str(total))
                if 'completed' in self.kpi_labels:
                    self.kpi_labels['completed'].config(text=str(completed))
                if 'in_progress' in self.kpi_labels:
                    self.kpi_labels['in_progress'].config(text=str(in_progress))
                if 'not_started' in self.kpi_labels:
                    self.kpi_labels['not_started'].config(text=str(not_started))
                if 'printed' in self.kpi_labels:
                    self.kpi_labels['printed'].config(text=str(printed))
                if 'with_invoice' in self.kpi_labels:
                    self.kpi_labels['with_invoice'].config(text=str(with_invoice))
                if 'total_items' in self.kpi_labels:
                    self.kpi_labels['total_items'].config(text=str(total_items))

                # === ГРАФИК 1: Статус сборки (Donut) ===
                self.ax_pie.clear()

                if total == 0:
                    sizes = [1]
                    colors_pie = [COLORS["card"]]
                else:
                    sizes = [completed, in_progress, not_started]
                    colors_pie = [COLORS["teal_card"], COLORS["orange_card"], COLORS["danger"]]

                wedges, _ = self.ax_pie.pie(
                    sizes, colors=colors_pie, startangle=90,
                    wedgeprops=dict(width=0.35, edgecolor=COLORS["card"])
                )
                self.ax_pie.text(0, 0, f"{total}", ha='center', va='center',
                                 fontsize=20, color="white", fontweight="bold")

                # Легенда
                legend_text = f"✓ Собрано: {completed}  |  ⏳ В работе: {in_progress}  |  ○ Не начато: {not_started}"
                if hasattr(self, 'pie_legend'):
                    self.pie_legend.config(text=legend_text)

                self.canvas_pie.draw_idle()

                # === ГРАФИК 2: По маршрутам (Bar) ===
                self.ax_bar.clear()

                if routes_count:
                    # Сортируем и берём топ-8
                    sorted_routes = sorted(routes_count.items(), key=lambda x: x[1], reverse=True)[:8]
                    route_names = [r[0][:15] for r in sorted_routes]  # Обрезаем длинные названия
                    route_values = [r[1] for r in sorted_routes]

                    bars = self.ax_bar.barh(route_names, route_values, color=COLORS["blue_card"], height=0.6)

                    # Добавляем значения на бары
                    for bar, val in zip(bars, route_values):
                        self.ax_bar.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                                        str(val), va='center', ha='left', color=COLORS["sub_text"], fontsize=8)

                    self.ax_bar.invert_yaxis()
                    self.ax_bar.set_xlim(0, max(route_values) * 1.2 if route_values else 10)

                # Стилизация
                self.ax_bar.tick_params(colors=COLORS["sub_text"], labelsize=8)
                self.ax_bar.spines['top'].set_visible(False)
                self.ax_bar.spines['right'].set_visible(False)
                self.ax_bar.spines['bottom'].set_color(COLORS["sub_text"])
                self.ax_bar.spines['left'].set_color(COLORS["sub_text"])

                self.canvas_bar.draw_idle()

        except Exception as e:
            import traceback
            traceback.print_exc()

    # ==========================================
    # LOGS TAB
    # ==========================================
    def create_logs_tab(self, parent):
        frame = ttk.Frame(parent, padding=0)
        frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(frame, bg=COLORS["log_bg"], fg=COLORS["log_fg"],
                                                  font=("Consolas", 11), state='disabled', bd=0)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        handler = ThreadSafeLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter('%(asctime)s > %(message)s', datefmt='%H:%M:%S'))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def check_log_queue(self):
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self.log_text.configure(state='normal')
                self.log_text.insert(tk.END, msg + '\n')
                self.log_text.see(tk.END)
                self.log_text.configure(state='disabled')
            except queue.Empty: break
        self.after(100, self.check_log_queue)

    # ==========================================
    # USERS TAB
    # ==========================================
    def create_users_tab(self, parent):
        frame = ttk.Frame(parent, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # Toolbar
        toolbar = tk.Frame(frame, bg=COLORS["bg"])
        toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(toolbar, text="🔌 Отключить выбранного", style="Danger.TButton",
                   command=self.disconnect_selected_user).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="🔄 Обновить", command=self.refresh_users_table).pack(side=tk.LEFT, padx=5)

        # Table
        cols = ('ID', 'Пользователь', 'Роль', 'Склад', 'Время')
        self.users_tree = ttk.Treeview(frame, columns=cols, show='headings')

        self.users_tree.heading('ID', text='Session ID')
        self.users_tree.heading('Пользователь', text='Пользователь')
        self.users_tree.heading('Роль', text='Роль')
        self.users_tree.heading('Склад', text='Склад')
        self.users_tree.heading('Время', text='Время входа')

        self.users_tree.column('ID', width=100)
        self.users_tree.column('Пользователь', width=150)
        self.users_tree.column('Роль', width=100)
        self.users_tree.column('Склад', width=100)
        self.users_tree.column('Время', width=100)

        self.users_tree.pack(fill=tk.BOTH, expand=True)
        self.users_tree.tag_configure('even', background=COLORS["table_row"], foreground=COLORS["header_text"])
        self.users_tree.tag_configure('odd', background=COLORS["table_row_alt"], foreground=COLORS["header_text"])

        # Double-click to disconnect
        self.users_tree.bind('<Double-1>', lambda e: self.disconnect_selected_user())

        # Context menu
        self.users_menu = tk.Menu(self, tearoff=0)
        self.users_menu.add_command(label="🔌 Отключить", command=self.disconnect_selected_user)
        self.users_menu.add_command(label="📋 Копировать ID", command=self.copy_session_id)
        self.users_tree.bind('<Button-3>', self.show_users_menu)

    def update_users_table(self, sessions):
        """Обновление таблицы пользователей. Сравнивает данные, чтобы таблица не мерцала."""
        # Сохраняем сессии для отключения
        self.current_sessions = sessions

        # 1. Собираем список текущих ID в таблице
        existing_ids = [self.users_tree.item(item)['values'][0] for item in self.users_tree.get_children()]

        # 2. Собираем список актуальных сессий (ID)
        current_ids = [s.session_id[:8] for s in sessions.values()]

        # 3. Если наборы ID совпадают — ничего не делаем (избегаем мерцания)
        if set(existing_ids) == set(current_ids):
            return

        # 4. Если есть изменения — перерисовываем
        self.users_tree.delete(*self.users_tree.get_children())

        for idx, s in enumerate(sessions.values()):
            # Форматируем время
            try:
                dt = datetime.fromisoformat(s.connected_at)
                time_str = dt.strftime('%H:%M:%S')
            except:
                time_str = s.connected_at

            self.users_tree.insert('', tk.END, iid=s.session_id, values=(
                s.session_id[:8],  # ID (кратко)
                s.username,        # Имя
                s.role,            # Роль
                s.warehouse_id or "-", # Склад
                time_str           # Время входа
            ), tags=('even' if idx % 2 == 0 else 'odd',))

    def show_users_menu(self, event):
        """Показать контекстное меню"""
        item = self.users_tree.identify_row(event.y)
        if item:
            self.users_tree.selection_set(item)
            self.users_menu.post(event.x_root, event.y_root)

    def copy_session_id(self):
        """Копировать ID сессии в буфер"""
        selected = self.users_tree.selection()
        if selected:
            session_id = selected[0]
            self.clipboard_clear()
            self.clipboard_append(session_id)
            logging.info(f"Session ID скопирован: {session_id}")

    def refresh_users_table(self):
        """Принудительное обновление таблицы"""
        if hasattr(self.server, 'sessions'):
            self.users_tree.delete(*self.users_tree.get_children())
            current_sessions = self.server.sessions.sessions
            for idx, s in enumerate(current_sessions.values()):
                try:
                    dt = datetime.fromisoformat(s.connected_at)
                    time_str = dt.strftime('%H:%M:%S')
                except:
                    time_str = s.connected_at
                self.users_tree.insert('', tk.END, iid=s.session_id, values=(
                    s.session_id[:8], s.username, s.role, s.warehouse_id or "-", time_str
                ), tags=('even' if idx % 2 == 0 else 'odd',))

    def disconnect_selected_user(self):
        """Отключить выбранного пользователя"""
        selected = self.users_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите пользователя для отключения")
            return

        session_id = selected[0]
        values = self.users_tree.item(session_id)['values']
        username = values[1] if len(values) > 1 else "Unknown"

        if not messagebox.askyesno("Подтверждение",
                                   f"Отключить пользователя {username}?\n\nЕго приложение будет закрыто."):
            return

        # Отключаем через сервер
        try:
            import asyncio
            import json

            # Находим websocket по session_id
            if hasattr(self.server, 'sessions'):
                sessions = self.server.sessions.sessions

                # sessions - это Dict[session_id, Session], где Session содержит websocket
                if session_id in sessions:
                    session = sessions[session_id]
                    websocket = session.websocket

                    # Отправляем команду на закрытие клиента
                    async def disconnect_client(ws, uname, sid):
                        try:
                            # Отправляем команду на закрытие приложения
                            await ws.send(json.dumps({
                                'type': 'force_disconnect',
                                'message': 'Администратор отключил вас от сервера',
                                'action': 'close_app'
                            }))
                            logging.info(f"Команда отключения отправлена: {uname} ({sid[:8]})")
                            # Закрываем соединение
                            await asyncio.sleep(0.5)
                            await ws.close(1000, "Disconnected by admin")
                        except Exception as e:
                            logging.error(f"Ошибка отключения: {e}")

                    # Запускаем в event loop сервера
                    if hasattr(self.server, 'loop') and self.server.loop:
                        asyncio.run_coroutine_threadsafe(
                            disconnect_client(websocket, username, session_id),
                            self.server.loop
                        )
                        logging.info(f"Пользователь {username} отключен администратором")
                        messagebox.showinfo("Готово", f"Пользователь {username} отключен")
                        return
                    else:
                        messagebox.showerror("Ошибка", "Event loop сервера недоступен")
                        return

            messagebox.showerror("Ошибка", "Сессия не найдена")

        except Exception as e:
            logging.error(f"Ошибка отключения пользователя: {e}")
            messagebox.showerror("Ошибка", f"Не удалось отключить: {e}")

    # ==========================================
    # CONTROL TAB
    # ==========================================
    def create_control_tab(self, parent):
        f = ttk.Frame(parent, padding=40)
        f.pack(fill=tk.BOTH, expand=True)
        
        ttk.Button(f, text="ОЧИСТИТЬ БАЗУ ДАННЫХ", style="Danger.TButton", command=self.run_repair).pack(fill=tk.X, pady=10)
        ttk.Button(f, text="СКАНИРОВАТЬ CSV", style="Action.TButton", command=lambda: self.server.csv_monitor.scan()).pack(fill=tk.X, pady=10)
        ttk.Button(f, text="ПЕРЕЗАГРУЗИТЬ UI", style="TButton", command=lambda: self.update()).pack(fill=tk.X, pady=10)

    def run_repair(self):
        if messagebox.askyesno("Внимание", "Удалить все заказы из базы?"):
            import subprocess
            subprocess.Popen(["python", "db_repair.py"], shell=True)
