#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WISO GOLABEL - Database Module
Handles all database operations for orders, users, logistics, production planning, and more.
"""

import sqlite3
import json
import hashlib
import math
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
import logging
from typing import Optional

# Database path - adjusted for backend/ subdirectory
DB_PATH = Path(__file__).parent.parent / "wiso_golabel.db"

# Logger setup
logger = logging.getLogger(__name__)

# ============================================
# USER CLASS
# ============================================
class User:
    """Simple User class to return authentication results"""
    def __init__(self, user_id, username, password_hash, role, warehouse_id, created_at, last_login, permissions='', first_name='', last_name='', display_name=''):
        self.user_id = user_id
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self.warehouse_id = warehouse_id
        self.created_at = created_at
        self.last_login = last_login
        self.permissions = permissions
        self.first_name = first_name or ''
        self.last_name = last_name or ''
        self.display_name = display_name or username

# ============================================
# DATABASE CLASS
# ============================================
class Database:
    def __init__(self, db_path):
        # ÐŸÐ¾Ð´Ð´ÐµÑ€Ð¶ÐºÐ° ÐºÐ°Ðº Path, Ñ‚Ð°Ðº Ð¸ ÑÑ‚Ñ€Ð¾ÐºÐ¸
        self.db_path = Path(db_path) if isinstance(db_path, str) else db_path
        logger.info(f"Database initialized with path: {self.db_path.absolute()}")
        self.init_database()
        self._ensure_communication_tables()

    def _ensure_communication_tables(self):
        """Create service communication tables (chat/tasks) if missing."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comm_dialogs (
                    dialog_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    is_group INTEGER DEFAULT 0,
                    created_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comm_dialog_members (
                    dialog_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (dialog_id, user_id)
                )
            
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comm_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dialog_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    message_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    edited_at TEXT
                )
            
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comm_tasks (
                    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    assigned_to INTEGER NOT NULL,
                    created_by INTEGER NOT NULL,
                    deadline_date TEXT,
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comm_message_reads (
                    message_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    read_at TEXT NOT NULL,
                    PRIMARY KEY (message_id, user_id)
                )
            
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comm_message_attachments (
                    message_id INTEGER PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    mime_type TEXT,
                    file_size INTEGER NOT NULL,
                    file_data BLOB NOT NULL,
                    created_at TEXT NOT NULL
                )
            
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comm_task_assignees (
                    task_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, user_id)
                )
            
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comm_task_watchers (
                    task_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, user_id)
                )
            
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comm_members_user ON comm_dialog_members(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comm_messages_dialog ON comm_messages(dialog_id, created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comm_tasks_assignee ON comm_tasks(assigned_to, status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comm_message_reads_user ON comm_message_reads(user_id, read_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comm_task_assignees_user ON comm_task_assignees(user_id, task_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comm_task_watchers_user ON comm_task_watchers(user_id, task_id)')
            cursor.execute('''
                INSERT OR IGNORE INTO comm_task_assignees (task_id, user_id, added_at)
                SELECT task_id, assigned_to, COALESCE(updated_at, created_at, ?)
                FROM comm_tasks
                WHERE assigned_to IS NOT NULL
            ''', (datetime.now().isoformat(),))
            conn.commit()
        except Exception as e:
            logger.error(f"Error creating communication tables: {e}")
            conn.rollback()
        finally:
            conn.close()


    def get_connection(self):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ Ðº Ð‘Ð”"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=15,                # Ð–Ð´Ð°Ñ‚ÑŒ Ð´Ð¾ 15 ÑÐµÐºÑƒÐ½Ð´ Ð¿Ñ€Ð¸ Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²ÐºÐµ (ÑÐµÑ‚ÐµÐ²Ð¾Ð¹ Ð´Ð¸ÑÐº)
            check_same_thread=False     # Ð Ð°Ð·Ñ€ÐµÑˆÐ¸Ñ‚ÑŒ Ð´Ð¾ÑÑ‚ÑƒÐ¿ Ð¸Ð· Ñ€Ð°Ð·Ð½Ñ‹Ñ… Ñ‚Ñ€ÐµÐ´Ð¾Ð² (executor)
        )
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def safe_connection(self):
        """ÐšÐ¾Ð½Ñ‚ÐµÐºÑÑ‚Ð½Ñ‹Ð¹ Ð¼ÐµÐ½ÐµÐ´Ð¶ÐµÑ€ â€” Ð³Ð°Ñ€Ð°Ð½Ñ‚Ð¸Ñ€ÑƒÐµÑ‚ Ð·Ð°ÐºÑ€Ñ‹Ñ‚Ð¸Ðµ ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ñ.

        Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ð½Ð¸Ðµ:
            with self.db.safe_connection() as conn:
                conn.execute(...)
                conn.commit()
        """
        conn = self.get_connection()
        try:
            yield conn
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def format_user_display_name(first_name: str, last_name: str, username: str) -> str:
        """Display label like 'K. Korol' with fallback to login."""
        fn = str(first_name or '').strip()
        ln = str(last_name or '').strip()
        un = str(username or '').strip()
        if fn and ln:
            return f"{fn[:1].upper()}. {ln}"
        if ln:
            return ln
        if fn:
            return fn
        return un

    def update_client_logistics(self, client_id, route_id, transport, point, rules=None):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð»Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÑƒ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð° + ÐŸÐ ÐÐ’Ð˜Ð›Ð ÐŸÐž Ð¡Ð£ÐœÐœÐ•"""
        conn = self.get_connection()
        try:
            # Ð•ÑÐ»Ð¸ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð° Ð¿ÐµÑ€ÐµÐ´Ð°Ð»Ð¸, ÑÐ¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð¸Ñ… ÐºÐ°Ðº JSON, Ð¸Ð½Ð°Ñ‡Ðµ Ð¾ÑÑ‚Ð°Ð²Ð»ÑÐµÐ¼ ÑÑ‚Ð°Ñ€Ñ‹Ðµ Ð¸Ð»Ð¸ NULL
            if rules is not None:
                rules_json = json.dumps(rules)
                conn.execute('''
                    UPDATE client_routes
                    SET route_id=?, transport_type=?, delivery_point=?, route_rules=?, updated_at=?
                    WHERE client_id=?
                ''', (route_id, transport, point, rules_json, datetime.now().isoformat(), client_id))
            else:
                conn.execute('''
                    UPDATE client_routes
                    SET route_id=?, transport_type=?, delivery_point=?, updated_at=?
                    WHERE client_id=?
                ''', (route_id, transport, point, datetime.now().isoformat(), client_id))

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating client logistics: {e}")
            return False
        finally:
            conn.close()

    def get_all_recipes(self) -> list:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ñ‹ (Ð´Ð»Ñ Ñ€Ð°ÑÑ‡ÐµÑ‚Ð° Ñ†ÐµÐ½ Ð¸ Ð¿Ð»Ð°Ð½Ð°)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM recipes ORDER BY article_nr')
            rows = cursor.fetchall()
            
            recipes = []
            for row in rows:
                # ÐŸÑ€ÐµÐ¾Ð±Ñ€Ð°Ð·ÑƒÐµÐ¼ ÑÑ‚Ñ€Ð¾ÐºÑƒ Ð‘Ð” Ð² ÑÐ»Ð¾Ð²Ð°Ñ€ÑŒ
                r = dict(row)
                recipes.append(r)
            return recipes
        except Exception as e:
            logger.error(f"Error getting all recipes: {e}")
            return []
        finally:
            conn.close()        

    def import_sales_history_bulk(self, data_list):
        """ÐœÐ°ÑÑÐ¾Ð²Ð°Ñ Ð²ÑÑ‚Ð°Ð²ÐºÐ° Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ð¸ Ð¿Ñ€Ð¾Ð´Ð°Ð¶"""
        conn = self.get_connection()
        try:
            conn.executemany('''
                INSERT OR REPLACE INTO sales_history (article_nr, sale_date, quantity)
                VALUES (?, ?, ?)
            ''', data_list)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° bulk Ð²ÑÑ‚Ð°Ð²ÐºÐ¸ Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ð¸: {e}")
            return False
        finally:
            conn.close()

    def init_database(self):
        """Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ñ Ð±Ð°Ð·Ñ‹ Ð´Ð°Ð½Ð½Ñ‹Ñ…"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # WAL mode: Ð¿Ð¾Ð·Ð²Ð¾Ð»ÑÐµÑ‚ Ñ‡Ð¸Ñ‚Ð°Ñ‚ÑŒ Ð¸Ð· Ð‘Ð” Ð¿Ð¾ÐºÐ° Ð¸Ð´Ñ‘Ñ‚ Ð·Ð°Ð¿Ð¸ÑÑŒ (ÐºÑ€Ð¸Ñ‚Ð¸Ñ‡Ð½Ð¾ Ð´Ð»Ñ Ð¿Ð°Ñ€Ð°Ð»Ð»ÐµÐ»ÑŒÐ½Ñ‹Ñ… Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¾Ð²)
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            wal_result = cursor.fetchone()
            logger.info(f"SQLite journal mode: {wal_result[0] if wal_result else 'unknown'}")
        except Exception as e:
            logger.warning(f"Could not set WAL mode: {e}")

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¹
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'operator', 'warehouse')),
                warehouse_id TEXT,
                first_name TEXT,
                last_name TEXT,
                display_name TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        ''')

        # 1. Ð¡Ð½Ð°Ñ‡Ð°Ð»Ð° ÐºÐ¾Ð¼Ð°Ð½Ð´Ð° ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ñ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ (Ð²ÐºÐ»ÑŽÑ‡Ð°ÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ðµ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ Ð½Ð° ÑÐ»ÑƒÑ‡Ð°Ð¹, ÐµÑÐ»Ð¸ Ð±Ð°Ð·Ñ‹ ÐµÑ‰Ðµ Ð½ÐµÑ‚)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                order_data TEXT NOT NULL,
                status TEXT NOT NULL,
                warehouse_id TEXT,
                printed INTEGER DEFAULT 0,
                delivery_date TEXT,      -- Ð”Ð¾Ð±Ð°Ð²Ð¸Ð»Ð¸ ÑÑŽÐ´Ð°
                production_date TEXT,    -- Ð”Ð¾Ð±Ð°Ð²Ð¸Ð»Ð¸ ÑÑŽÐ´Ð°
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        # 2. Ð¢Ð•ÐŸÐ•Ð Ð¬ ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯ (Ð´Ð»Ñ Ñ‚ÐµÑ…, Ñƒ ÐºÐ¾Ð³Ð¾ Ð±Ð°Ð·Ð° ÑƒÐ¶Ðµ Ð±Ñ‹Ð»Ð° ÑÐ¾Ð·Ð´Ð°Ð½Ð° Ñ€Ð°Ð½ÑŒÑˆÐµ)
        # Ð­Ñ‚Ð¾Ñ‚ ÐºÐ¾Ð´ Ð¸Ð´ÐµÑ‚ ÐžÐ¢Ð”Ð•Ð›Ð¬ÐÐž, Ð° Ð½Ðµ Ð²Ð½ÑƒÑ‚Ñ€Ð¸ ÐºÐ°Ð²Ñ‹Ñ‡ÐµÐº Ð²Ñ‹ÑˆÐµ!
        try:
            cursor.execute("PRAGMA table_info(orders)")
            columns = [info[1] for info in cursor.fetchall()]

            if 'delivery_date' not in columns:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ ÐºÐ¾Ð»Ð¾Ð½ÐºÑƒ delivery_date Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ orders...")
                cursor.execute("ALTER TABLE orders ADD COLUMN delivery_date TEXT")

            if 'production_date' not in columns:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ ÐºÐ¾Ð»Ð¾Ð½ÐºÑƒ production_date Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ orders...")
                cursor.execute("ALTER TABLE orders ADD COLUMN production_date TEXT")


            conn.commit()
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ñ€Ð¸ Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ ÐºÐ¾Ð»Ð¾Ð½Ð¾Ðº Ð´Ð°Ñ‚: {e}")

        # 3. Ð¢ÐµÐ¿ÐµÑ€ÑŒ ÑÐ¾Ð·Ð´Ð°ÐµÐ¼ Ð¸Ð½Ð´ÐµÐºÑÑ‹ (ÐºÐ¾Ð³Ð´Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ Ñ‚Ð¾Ñ‡Ð½Ð¾ ÐµÑÑ‚ÑŒ)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_delivery ON orders(delivery_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_production ON orders(production_date)')


        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¾ÑˆÐ¸Ð±Ð¾Ðº
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS errors (
                error_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL
            )
        ''')

        # 1. Ð¡Ð¿ÐµÑ†Ð¸Ñ„Ð¸ÐºÐ°Ñ†Ð¸Ñ (BOM)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recipe_components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_article_nr TEXT,
                component_name TEXT,
                quantity REAL,
                unit TEXT,
                FOREIGN KEY(parent_article_nr) REFERENCES recipes(article_nr)
            )
        ''')

        # 2. Ð˜ÑÑ‚Ð¾Ñ€Ð¸Ñ Ð¿Ñ€Ð¾Ð´Ð°Ð¶ (Ð´Ð»Ñ 52 Ð½ÐµÐ´ÐµÐ»ÑŒ)
        # Ð£Ð”ÐÐ›Ð•ÐÐž: Ð¡Ñ‚Ð°Ñ€Ð°Ñ ÑÑ‚Ñ€ÑƒÐºÑ‚ÑƒÑ€Ð° Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ sales_history
        # ÐÐ¾Ð²Ð°Ñ ÑÑ‚Ñ€ÑƒÐºÑ‚ÑƒÑ€Ð° ÑÐ¾Ð·Ð´Ð°ÐµÑ‚ÑÑ Ð½Ð¸Ð¶Ðµ (ÑÑ‚Ñ€Ð¾ÐºÐ° ~459) Ñ Ð¿Ð¾Ð»Ð½Ñ‹Ð¼ Ð½Ð°Ð±Ð¾Ñ€Ð¾Ð¼ Ð¿Ð¾Ð»ÐµÐ¹:
        # sale_id, sale_date, article_nr, quantity, order_id, warehouse_user, created_at, updated_at

        # 3. Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð’Ð¸Ñ€Ñ‚ÑƒÐ°Ð»ÑŒÐ½Ñ‹Ñ… ÐžÑÑ‚Ð°Ñ‚ÐºÐ¾Ð² (Ð²Ð¼ÐµÑÑ‚Ð¾ JSON)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS virtual_stock (
                article_nr TEXT PRIMARY KEY,
                quantity REAL DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¿Ñ€Ð°Ð²Ð¸Ð» Ñ€Ð°ÑÐ¿Ñ€ÐµÐ´ÐµÐ»ÐµÐ½Ð¸Ñ Ð½Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ (Production Leveling)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS production_rules (
                category TEXT PRIMARY KEY,    -- ÐšÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ (Biskuit, Medowik)
                days_offset TEXT,             -- JSON: "{-1: 0.3, -2: 0.4}"
                updated_at TEXT
            )
        ''')

        # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ Ð±Ð°Ð·Ð¾Ð²Ñ‹Ðµ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð° (ÐµÑÐ»Ð¸ Ð¿ÑƒÑÑ‚Ð¾)
        cursor.execute("SELECT COUNT(*) FROM production_rules")
        if cursor.fetchone()[0] == 0:
            defaults = [
                # Ð‘Ð¸ÑÐºÐ²Ð¸Ñ‚: 50% Ð·Ð° Ð´ÐµÐ½ÑŒ Ð´Ð¾ Ð¾Ñ‚Ð³Ñ€ÑƒÐ·ÐºÐ¸, 50% Ð·Ð° Ð´Ð²Ð° Ð´Ð½Ñ
                ('Biskuit', '{"-1": 0.5, "-2": 0.5}'),
                # ÐœÐµÐ´Ð¾Ð²Ð¸Ðº: Ð”Ð¾Ð»ÑŒÑˆÐµ Ð¿Ñ€Ð¾Ð¿Ð¸Ñ‚Ñ‹Ð²Ð°ÐµÑ‚ÑÑ. 40% Ð·Ð° 2 Ð´Ð½Ñ, 60% Ð·Ð° 3 Ð´Ð½Ñ
                ('Medowik', '{"-2": 0.4, "-3": 0.6}'),
                # ÐœÐµÐ»Ð¾Ñ‡ÐµÐ²ÐºÐ°: Ð”ÐµÐ»Ð°ÐµÐ¼ Ð±Ñ‹ÑÑ‚Ñ€Ð¾, 100% Ð·Ð° 1 Ð´ÐµÐ½ÑŒ
                ('KleingebÃ¤ck', '{"-1": 1.0}'),
                # ÐžÑÑ‚Ð°Ð»ÑŒÐ½Ð¾Ðµ: ÐŸÐ¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ Ð·Ð° 1 Ð´ÐµÐ½ÑŒ
                ('default', '{"-1": 1.0}')
            ]
            for cat, rules in defaults:
                cursor.execute(
                    "INSERT INTO production_rules (category, days_offset, updated_at) VALUES (?, ?, ?)",
                    (cat, rules, datetime.now().isoformat())
                )
            conn.commit()
            logger.info("Created default production leveling rules")


        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð»Ð¾Ð³Ð¾Ð²
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL
            )
        ''')

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ ÐºÐ¾Ð»Ð¾Ð½ÐºÑƒ 'category' Ð² recipes, ÐµÑÐ»Ð¸ ÐµÑ‘ Ð½ÐµÑ‚ ---
        try:
            cursor.execute("PRAGMA table_info(recipes)")
            columns = [info[1] for info in cursor.fetchall()]

            if 'category' not in columns:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ Ð‘Ð”: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ ÐºÐ¾Ð»Ð¾Ð½ÐºÑƒ 'category' Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ recipes...")
                cursor.execute("ALTER TABLE recipes ADD COLUMN category TEXT DEFAULT 'Biskuit'")
                conn.commit() # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ðµ ÑÑ‚Ñ€ÑƒÐºÑ‚ÑƒÑ€Ñ‹
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ Ð‘Ð”: {e}")

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ð¸ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS print_history (
                print_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                printed_at TEXT NOT NULL,
                label_language TEXT,
                boxes_count INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ñ… Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² (ÐºÐ¾Ñ‚Ð¾Ñ€Ñ‹Ðµ Ð¿ÐµÑ‡Ð°Ñ‚Ð°ÑŽÑ‚ÑÑ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ñ€Ð¸ Ð½ÐµÐ¾Ð±Ñ…Ð¾Ð´Ð¸Ð¼Ð¾ÑÑ‚Ð¸)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conditional_articles (
                article_id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_number TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL
            )
        ''')

        # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð´ÐµÑ„Ð¾Ð»Ñ‚Ð½Ñ‹Ðµ ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñ‹ ÐµÑÐ»Ð¸ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¿ÑƒÑÑ‚Ð°Ñ
        cursor.execute("SELECT COUNT(*) FROM conditional_articles")
        if cursor.fetchone()[0] == 0:
            default_articles = [
                '05530', '05590', '05502', '05571',
                '05567', '05534', '05546'
            ]
            for article in default_articles:
                cursor.execute('''
                    INSERT INTO conditional_articles (article_number, description, created_at)
                    VALUES (?, ?, ?)
                ''', (article, 'ÐÑ€Ñ‚Ð¸ÐºÑƒÐ» Ñ Ð³Ð¾Ñ‚Ð¾Ð²Ñ‹Ð¼Ð¸ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ°Ð¼Ð¸', datetime.now().isoformat()))
            logger.info(f"Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¾ {len(default_articles)} ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ñ… Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ")

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¿Ñ€Ð¾Ð³Ñ€ÐµÑÑÐ° ÐºÐ¾Ð¼Ð¿Ð»ÐµÐºÑ‚Ð°Ñ†Ð¸Ð¸ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_picking (
                picking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                artikel_nr TEXT NOT NULL,
                pos INTEGER NOT NULL,
                total_qty INTEGER NOT NULL,
                picked_qty INTEGER DEFAULT 0,
                checked BOOLEAN DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE(order_id, artikel_nr)
            )
        ''')

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ð¹ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¹ Ð½Ð° Ð·Ð°ÐºÐ°Ð·Ñ‹
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS order_assignments (
                assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                assigned_at TEXT NOT NULL,
                status TEXT DEFAULT 'picking',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ð¸ Ð¿Ñ€Ð¾Ð´Ð°Ð¶ (Ð´Ð»Ñ ÑƒÑ‡ÐµÑ‚Ð° Ð¸ Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales_history (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_date TEXT NOT NULL,
                article_nr TEXT NOT NULL,
                quantity REAL NOT NULL,
                order_id TEXT,
                warehouse_user TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sale_date, article_nr, order_id)
            )
        ''')

        # Ð˜Ð½Ð´ÐµÐºÑ Ð´Ð»Ñ Ð±Ñ‹ÑÑ‚Ñ€Ð¾Ð³Ð¾ Ð¿Ð¾Ð¸ÑÐºÐ° Ð¿Ð¾ Ð´Ð°Ñ‚Ðµ Ð¸ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñƒ
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_sales_history_date_article
            ON sales_history(sale_date, article_nr)
        ''')

        # ÐžÑ‡Ð¸ÑÑ‚ÐºÐ° ÑÑ‚Ð°Ñ€Ð¾Ð¹ Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ð¸ (ÑÑ‚Ð°Ñ€ÑˆÐµ Ð³Ð¾Ð´Ð°) Ð¿Ñ€Ð¸ Ð·Ð°Ð¿ÑƒÑÐºÐµ
        cursor.execute("DELETE FROM sales_history WHERE sale_date < date('now', '-365 days')")
        conn.commit()

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð¾Ð² Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ Ñ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð°Ð¼Ð¸
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logistics_routes (
                route_id TEXT PRIMARY KEY,
                route_name TEXT NOT NULL,
                delivery_days TEXT NOT NULL,
                lead_time INTEGER DEFAULT 1,
                is_manual BOOLEAN DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        ''')

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ñ‚Ð¸Ð¿Ð¾Ð² Ñ‚ÐµÑÑ‚Ð° (Dough Types)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dough_types (
                dough_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                batch_size REAL DEFAULT 1.0,  -- ÐŸÑ€Ð¾Ñ‚Ð¸Ð²Ð½ÐµÐ¹ Ñ Ð¾Ð´Ð½Ð¾Ð³Ð¾ Ð·Ð°Ð¼ÐµÑÐ° (Charge)
                updated_at TEXT
            )
        ''')

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² (Ð¡Ð²ÑÐ·ÑŒ ÐÑ€Ñ‚Ð¸ÐºÑƒÐ» -> Ð¢ÐµÑÑ‚Ð¾)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recipes (
                article_nr TEXT PRIMARY KEY,
                name TEXT,                    -- ÐÐ°Ð·Ð²Ð°Ð½Ð¸Ðµ Ñ‚Ð¾Ñ€Ñ‚Ð° (Ð´Ð»Ñ ÑƒÐ´Ð¾Ð±ÑÑ‚Ð²Ð°)
                dough_id TEXT,                -- Ð¡ÑÑ‹Ð»ÐºÐ° Ð½Ð° dough_types
                items_per_tray REAL DEFAULT 1.0, -- Ð¨Ñ‚ÑƒÐº Ð½Ð° Ð¿Ñ€Ð¾Ñ‚Ð¸Ð²ÐµÐ½ÑŒ
                packaging_id TEXT,            -- ID ÐšÐ¾Ñ€Ð¾Ð±ÐºÐ¸
                composition TEXT,             -- Ð¡Ð¾ÑÑ‚Ð°Ð² Ð² JSON Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ðµ
                comments TEXT,                -- ÐšÐ¾Ð¼Ð¼ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð¸
                updated_at TEXT,
                FOREIGN KEY (dough_id) REFERENCES dough_types(dough_id)
            )
        ''')

        # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ Ð±Ð°Ð·Ð¾Ð²Ñ‹Ðµ Ñ‚Ð¸Ð¿Ñ‹ Ñ‚ÐµÑÑ‚Ð° (Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð½Ðµ Ð±Ñ‹Ð»Ð¾ Ð¿ÑƒÑÑ‚Ð¾)
        cursor.execute("SELECT COUNT(*) FROM dough_types")
        if cursor.fetchone()[0] == 0:
            defaults = [
                ('biskuit_hell', 'Ð‘Ð¸ÑÐºÐ²Ð¸Ñ‚ ÑÐ²ÐµÑ‚Ð»Ñ‹Ð¹', 10.0),
                ('biskuit_dunkel', 'Ð‘Ð¸ÑÐºÐ²Ð¸Ñ‚ Ñ‚ÐµÐ¼Ð½Ñ‹Ð¹ (Ð¨Ð¾ÐºÐ¾)', 10.0),
                ('napoleon', 'Ð¡Ð»Ð¾ÐµÐ½Ð¾Ðµ (ÐÐ°Ð¿Ð¾Ð»ÐµÐ¾Ð½)', 4.0),
                ('medowik', 'ÐœÐµÐ´Ð¾Ð²Ð¸Ðº', 20.0),
                ('sand', 'ÐŸÐµÑÐ¾Ñ‡Ð½Ð¾Ðµ', 5.0)
            ]
            for did, name, size in defaults:
                cursor.execute(
                    "INSERT INTO dough_types (dough_id, name, batch_size, updated_at) VALUES (?, ?, ?, ?)",
                    (did, name, size, datetime.now().isoformat())
                )

        # ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð´Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ composition Ð¸ comments ÐµÑÐ»Ð¸ Ð¸Ñ… Ð½ÐµÑ‚
        try:
            cursor.execute("PRAGMA table_info(recipes)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'composition' not in columns:
                cursor.execute("ALTER TABLE recipes ADD COLUMN composition TEXT")
                logger.info("Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° 'composition' Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ recipes")

            if 'comments' not in columns:
                cursor.execute("ALTER TABLE recipes ADD COLUMN comments TEXT")
                logger.info("Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° 'comments' Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ recipes")

            if 'freeze_mode' not in columns:
                cursor.execute("ALTER TABLE recipes ADD COLUMN freeze_mode TEXT DEFAULT ''")
                logger.info("Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° 'freeze_mode' Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ recipes")
        except Exception as e:
            logger.warning(f"ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ recipes: {e}")

        # ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð´Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ resource_id Ð² dough_types
        try:
            cursor.execute("PRAGMA table_info(dough_types)")
            dough_columns = [row[1] for row in cursor.fetchall()]

            if 'resource_id' not in dough_columns:
                cursor.execute("ALTER TABLE dough_types ADD COLUMN resource_id INTEGER DEFAULT 1")
                logger.info("Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° 'resource_id' Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ dough_types")

            if 'unit' not in dough_columns:
                cursor.execute("ALTER TABLE dough_types ADD COLUMN unit TEXT DEFAULT 'Ð»Ð¸ÑÑ‚'")
                logger.info("Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° 'unit' Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ dough_types")

            if 'workshop' not in dough_columns:
                cursor.execute("ALTER TABLE dough_types ADD COLUMN workshop TEXT DEFAULT 'ÐžÑÐ½Ð¾Ð²Ð½Ð¾Ð¹ Ñ†ÐµÑ…'")
                logger.info("Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° 'workshop' Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ dough_types")
        except Exception as e:
            logger.warning(f"ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ dough_types: {e}")

        # ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚Ðµ Ð±Ð»Ð¾Ðº ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ñ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ orders Ð² init_database
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                order_data TEXT NOT NULL,
                status TEXT NOT NULL,
                warehouse_id TEXT,
                printed INTEGER DEFAULT 0,
                delivery_date TEXT,      -- ÐÐžÐ’ÐÐ¯ ÐšÐžÐ›ÐžÐÐšÐ
                production_date TEXT,    -- ÐÐžÐ’ÐÐ¯ ÐšÐžÐ›ÐžÐÐšÐ
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ Ð¸Ð½Ð´ÐµÐºÑÑ‹ Ð´Ð»Ñ Ð¼Ð³Ð½Ð¾Ð²ÐµÐ½Ð½Ð¾Ð³Ð¾ Ð¿Ð¾Ð¸ÑÐºÐ°
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_delivery ON orders(delivery_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_production ON orders(production_date)')

        # Ð¡Ð¾Ð·Ð´Ð°Ñ‘Ð¼ ÑÑ‚Ð°Ð½Ð´Ð°Ñ€Ñ‚Ð½Ñ‹Ðµ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ñ‹ ÐµÑÐ»Ð¸ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¿ÑƒÑÑ‚Ð°Ñ
        cursor.execute("SELECT COUNT(*) FROM logistics_routes")
        if cursor.fetchone()[0] == 0:
            default_routes = [
                ('ost', 'Ost', '[0, 2, 4]', 1, 0),           # ÐŸÐ½, Ð¡Ñ€, ÐŸÑ‚
                ('sued', 'SÃ¼d', '[1, 3]', 1, 0),             # Ð’Ñ‚, Ð§Ñ‚
                ('west', 'West', '[0, 3]', 1, 0),            # ÐŸÐ½, Ð§Ñ‚
                ('nord', 'Nord', '[1, 4]', 1, 0),            # Ð’Ñ‚, ÐŸÑ‚
                ('mitte', 'Mitte', '[0, 2, 4]', 1, 0),       # ÐŸÐ½, Ð¡Ñ€, ÐŸÑ‚
                ('free', 'Ð¡Ð²Ð¾Ð±Ð¾Ð´Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ñ‹', '[]', 1, 1),    # Ð‘ÐµÐ· Ñ„Ð¸ÐºÑÐ¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ñ‹Ñ… Ð´Ð½ÐµÐ¹ (Ñ€ÑƒÑ‡Ð½Ð¾Ð¹ Ñ€ÐµÐ¶Ð¸Ð¼)
            ]
            for route_id, route_name, days, lead, manual in default_routes:
                cursor.execute('''
                    INSERT INTO logistics_routes (route_id, route_name, delivery_days, lead_time, is_manual, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (route_id, route_name, days, lead, manual, datetime.now().isoformat()))
            logger.info(f"Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¾ {len(default_routes)} Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð¾Ð² Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ")

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¿Ñ€Ð¸Ð²ÑÐ·ÐºÐ¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² Ðº Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°Ð¼
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client_routes (
                client_id TEXT PRIMARY KEY,
                client_name TEXT,
                email TEXT,
                first_name TEXT,
                last_name TEXT,
                company_name TEXT,
                website_url TEXT,
                vat_id TEXT,
                phone TEXT,
                position_title TEXT,
                route_id TEXT NOT NULL,
                country TEXT,
                price_list TEXT,
                discount_enabled INTEGER DEFAULT 0,
                discount_percent REAL DEFAULT 0,
                payment_terms TEXT,
                tags TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (route_id) REFERENCES logistics_routes(route_id)
            )
        ''')

        # Ð¡Ð¾Ð·Ð´Ð°Ñ‘Ð¼ Ð°Ð´Ð¼Ð¸Ð½Ð° Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ ÐµÑÐ»Ð¸ ÐµÐ³Ð¾ Ð½ÐµÑ‚
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        if cursor.fetchone()[0] == 0:
            admin_password = hashlib.sha256("admin123".encode()).hexdigest()
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, warehouse_id, first_name, last_name, display_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('admin', admin_password, 'admin', None, 'Admin', '', 'Admin', datetime.now().isoformat()))
            logger.info("Ð¡Ð¾Ð·Ð´Ð°Ð½ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒ Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ: admin / admin123")

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ Ð°Ð´Ñ€ÐµÑÐ° Ð² client_routes ---
        try:
            cursor.execute("PRAGMA table_info(client_routes)")
            existing_cols = [info[1] for info in cursor.fetchall()]

            # Ð¡Ð¿Ð¸ÑÐ¾Ðº ÐºÐ¾Ð»Ð¾Ð½Ð¾Ðº, ÐºÐ¾Ñ‚Ð¾Ñ€Ñ‹Ðµ Ð´Ð¾Ð»Ð¶Ð½Ñ‹ Ð±Ñ‹Ñ‚ÑŒ
            needed_cols = ['address', 'plz', 'city', 'email']

            extended_cols = {
                'first_name': "TEXT",
                'last_name': "TEXT",
                'company_name': "TEXT",
                'website_url': "TEXT",
                'vat_id': "TEXT",
                'phone': "TEXT",
                'position_title': "TEXT",
                'country': "TEXT",
                'price_list': "TEXT",
                'discount_enabled': "INTEGER DEFAULT 0",
                'discount_percent': "REAL DEFAULT 0",
                'payment_terms': "TEXT",
                'tags': "TEXT",
            }
            needed_cols.extend([k for k in extended_cols.keys() if k not in needed_cols])


            for col in needed_cols:
                if col not in existing_cols:
                    logger.info(f"ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ Ð‘Ð”: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ ÐºÐ¾Ð»Ð¾Ð½ÐºÑƒ '{col}' Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ client_routes...")
                    col_def = extended_cols.get(col, 'TEXT')
                    cursor.execute(f"ALTER TABLE client_routes ADD COLUMN {col} {col_def}")

        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ client_routes: {e}")

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ Ð´Ð»Ñ Ð¢Ñ€Ð°Ð½ÑÐ¿Ð¾Ñ€Ñ‚Ð° Ð¸ Ð¢Ð¾Ñ‡ÐºÐ¸ ---
        try:
            cursor.execute("PRAGMA table_info(client_routes)")
            cols = [col[1] for col in cursor.fetchall()]

            if 'transport_type' not in cols:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ transport_type...")
                cursor.execute("ALTER TABLE client_routes ADD COLUMN transport_type TEXT DEFAULT 'Eigenes Auto'")

            if 'delivery_point' not in cols:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ delivery_point...")
                cursor.execute("ALTER TABLE client_routes ADD COLUMN delivery_point TEXT DEFAULT 'GeschÃ¤ft'")

        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ Ð‘Ð” Ð»Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÐ¸: {e}")

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ is_new Ð´Ð»Ñ Ð¾Ñ‚ÑÐ»ÐµÐ¶Ð¸Ð²Ð°Ð½Ð¸Ñ Ð½Ð¾Ð²Ñ‹Ñ… ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² ---
        try:
            cursor.execute("PRAGMA table_info(client_routes)")
            cols = [col[1] for col in cursor.fetchall()]

            if 'is_new' not in cols:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ is_new Ð² client_routes...")
                cursor.execute("ALTER TABLE client_routes ADD COLUMN is_new INTEGER DEFAULT 0")
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ is_new client_routes: {e}")

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ is_new Ð´Ð»Ñ Ð¾Ñ‚ÑÐ»ÐµÐ¶Ð¸Ð²Ð°Ð½Ð¸Ñ Ð½Ð¾Ð²Ñ‹Ñ… Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² ---
        try:
            cursor.execute("PRAGMA table_info(recipes)")
            cols = [col[1] for col in cursor.fetchall()]

            if 'is_new' not in cols:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ is_new Ð² recipes...")
                cursor.execute("ALTER TABLE recipes ADD COLUMN is_new INTEGER DEFAULT 0")
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ is_new recipes: {e}")

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: Ð”Ð°Ð½Ð½Ñ‹Ðµ ÑÑ‚Ð¸ÐºÐµÑ‚ÐºÐ¸ (Label) Ð´Ð»Ñ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² ---
        try:
            cursor.execute("PRAGMA table_info(recipes)")
            cols = [col[1] for col in cursor.fetchall()]

            for col_name, col_type in [
                ('label_name', 'TEXT'),
                ('label_full_name', 'TEXT'),
                ('barcode', 'TEXT'),
                ('weight_grams', 'REAL'),
                ('shelf_life_days', 'INTEGER'),
                ('nutrition_energie', 'TEXT'),
                ('nutrition_fett', 'TEXT'),
                ('nutrition_davon_fett', 'TEXT'),
                ('nutrition_kohlenhydrate', 'TEXT'),
                ('nutrition_davon_zucker', 'TEXT'),
                ('nutrition_eiweiss', 'TEXT'),
                ('nutrition_salz', 'TEXT'),
            ]:
                if col_name not in cols:
                    logger.info(f"ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ {col_name} Ð² recipes...")
                    cursor.execute(f"ALTER TABLE recipes ADD COLUMN {col_name} {col_type}")
            conn.commit()
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ label recipes: {e}")

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: ÐŸÑ€Ð°Ð²Ð° Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð° (Permissions) ---
        try:
            cursor.execute("PRAGMA table_info(users)")
            cols = [col[1] for col in cursor.fetchall()]

            if 'permissions' not in cols:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ permissions Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ users...")
                cursor.execute("ALTER TABLE users ADD COLUMN permissions TEXT")

                # ÐšÐ¾Ð½Ð²ÐµÑ€Ñ‚Ð¸Ñ€ÑƒÐµÐ¼ ÑÑ‚Ð°Ñ€Ñ‹Ðµ Ñ€Ð¾Ð»Ð¸ Ð² Ð¿Ñ€Ð°Ð²Ð° (Ð´Ð»Ñ ÑÐ¾Ð²Ð¼ÐµÑÑ‚Ð¸Ð¼Ð¾ÑÑ‚Ð¸)
                cursor.execute("UPDATE users SET permissions = 'admin,orders,logistics,production,warehouse' WHERE role = 'admin'")
                cursor.execute("UPDATE users SET permissions = 'orders' WHERE role = 'operator'")
                cursor.execute("UPDATE users SET permissions = 'warehouse' WHERE role = 'warehouse'")

            if 'first_name' not in cols:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ first_name Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ users...")
                cursor.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
            if 'last_name' not in cols:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ last_name Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ users...")
                cursor.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
            if 'display_name' not in cols:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ display_name Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ users...")
                cursor.execute("ALTER TABLE users ADD COLUMN display_name TEXT")

            # Backfill display_name for existing rows if missing.
            cursor.execute("""
                UPDATE users
                SET display_name = username
                WHERE display_name IS NULL OR trim(display_name) = ''
            """)
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ Ð¿Ñ€Ð°Ð²: {e}")

        # ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð¿ÐµÑ€ÐµÐ½Ð¾ÑÐ¸Ð¼ Ð´Ð°Ñ‚Ñ‹ Ð¸Ð· JSON Ð² ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ Ð´Ð»Ñ Ð²ÑÐµÑ… ÑÑ‚Ð°Ñ€Ñ‹Ñ… Ð·Ð°Ð¿Ð¸ÑÐµÐ¹
        cursor.execute("SELECT order_id, order_data FROM orders WHERE delivery_date IS NULL")
        old_orders = cursor.fetchall()
        for row in old_orders:
            try:
                data = json.loads(row[1])
                d_date = data.get('delivery_date')
                p_date = data.get('production_date')
                if d_date:
                    cursor.execute("UPDATE orders SET delivery_date = ?, production_date = ? WHERE order_id = ?",
                                   (d_date, p_date, row[0]))
            except:
                continue

        # --- ÐÐ•Ð”ÐžÐ¡Ð¢ÐÐ®Ð©Ð˜Ð• Ð¢ÐÐ‘Ð›Ð˜Ð¦Ð« Ð”Ð›Ð¯ ÐŸÐ ÐžÐ˜Ð—Ð’ÐžÐ”Ð¡Ð¢Ð’Ð ---
        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº Ð¿Ð»Ð°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS plan_settings (
                user_id INTEGER,
                setting_key TEXT,
                setting_value TEXT,
                updated_at TEXT,
                PRIMARY KEY (user_id, setting_key)
            )
        ''')

        # Ð’ÐÐ–ÐÐž: ÐžÑ‡Ð¸ÑÑ‚ÐºÐ° Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ð¾Ð² workdays Ñ NULL user_id (SQLite Ð½Ðµ ÑÑ‡Ð¸Ñ‚Ð°ÐµÑ‚ NULL=NULL)
        # ÐžÑÑ‚Ð°Ð²Ð»ÑÐµÐ¼ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ ÑÐ°Ð¼ÑƒÑŽ Ð½Ð¾Ð²ÑƒÑŽ Ð·Ð°Ð¿Ð¸ÑÑŒ
        try:
            cursor.execute('''
                DELETE FROM plan_settings
                WHERE user_id IS NULL AND setting_key = 'workdays'
                AND rowid NOT IN (
                    SELECT MAX(rowid) FROM plan_settings
                    WHERE user_id IS NULL AND setting_key = 'workdays'
                )
            ''')
            if cursor.rowcount > 0:
                logger.info(f"Cleaned up {cursor.rowcount} duplicate workdays settings")
        except Exception as e:
            logger.warning(f"Could not clean up duplicate workdays: {e}")

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ñ„Ð°ÐºÑ‚Ð¾Ð² Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð°
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS production_facts (
                date TEXT,
                article_nr TEXT,
                fact_qty REAL,
                PRIMARY KEY (date, article_nr)
            )
        ''')

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° ÐµÐ¶ÐµÐ´Ð½ÐµÐ²Ð½Ñ‹Ñ… Ð¾Ñ‚Ñ‡ÐµÑ‚Ð¾Ð² ÑÐºÐ»Ð°Ð´Ð° (Ð¸Ð½Ð²ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð·Ð°Ñ†Ð¸Ñ)
        # Ð”ÐžÐ‘ÐÐ’Ð›Ð•ÐÐž ÐŸÐžÐ›Ð• last_editor
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stock_reports (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                article_nr TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 0,
                last_editor TEXT, 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, article_nr)
            )
        ''')
        
        # ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ Ð´Ð»Ñ ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ñ… Ð±Ð°Ð· (ÐµÑÐ»Ð¸ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ Ð½ÐµÑ‚)
        try:
            cursor.execute("ALTER TABLE daily_stock_reports ADD COLUMN last_editor TEXT")
        except: pass

        # Ð˜Ð½Ð´ÐµÐºÑ Ð´Ð»Ñ Ð±Ñ‹ÑÑ‚Ñ€Ð¾Ð³Ð¾ Ð¿Ð¾Ð¸ÑÐºÐ° Ð¾Ñ‚Ñ‡ÐµÑ‚Ð¾Ð² Ð¿Ð¾ Ð´Ð°Ñ‚Ðµ
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_daily_stock_date
            ON daily_stock_reports(date)
        ''')

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð·Ð°Ñ„Ð¸ÐºÑÐ¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ð¾Ð³Ð¾ Ð¿Ð»Ð°Ð½Ð° Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð° Ð¿Ð¾ Ð´Ð½ÑÐ¼
        # ÐŸÑ€Ð¸ Ð²Ð²Ð¾Ð´Ðµ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¾Ð² - Ð¿Ñ€Ð¾ÑˆÐµÐ´ÑˆÐ¸Ðµ Ð´Ð½Ð¸ Ñ„Ð¸ÐºÑÐ¸Ñ€ÑƒÑŽÑ‚ÑÑ Ð¸ Ð½Ðµ Ð¿ÐµÑ€ÐµÑÑ‡Ð¸Ñ‚Ñ‹Ð²Ð°ÑŽÑ‚ÑÑ
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS locked_production_plan (
                date TEXT NOT NULL,
                article_nr TEXT NOT NULL,
                locked_qty REAL NOT NULL,
                locked_by TEXT,
                locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (date, article_nr)
            )
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_locked_plan_date
            ON locked_production_plan(date)
        ''')

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¿Ð¾Ñ‚Ñ€ÐµÐ±Ð»ÐµÐ½Ð¸Ñ Ñ€ÐµÑÑƒÑ€ÑÐ¾Ð²
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_resource_consumption (
                article_nr TEXT,
                resource_id INTEGER,
                time_needed_min REAL,
                comments TEXT,
                created_at TEXT,
                updated_at TEXT,
                PRIMARY KEY (article_nr, resource_id)
            )
        ''')

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¹ (Ñ†ÐµÑ…Ð¾Ð²)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id TEXT UNIQUE,
                category_name TEXT,
                workshop_name TEXT,
                description TEXT,
                color TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Ð¡Ð¾Ð·Ð´Ð°Ñ‘Ð¼ Ð±Ð°Ð·Ð¾Ð²Ñ‹Ðµ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¸ ÐµÑÐ»Ð¸ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¿ÑƒÑÑ‚Ð°Ñ
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            default_categories = [
                ('biskuit', 'Ð‘Ð¸ÑÐºÐ²Ð¸Ñ‚', 'ÐžÑÐ½Ð¾Ð²Ð½Ð¾Ð¹ Ñ†ÐµÑ…', 'Ð‘Ð¸ÑÐºÐ²Ð¸Ñ‚Ð½Ñ‹Ðµ Ñ‚Ð¾Ñ€Ñ‚Ñ‹', '#FFE5B4'),
                ('medowik', 'ÐœÐµÐ´Ð¾Ð²Ð¸Ðº', 'ÐžÑÐ½Ð¾Ð²Ð½Ð¾Ð¹ Ñ†ÐµÑ…', 'ÐœÐµÐ´Ð¾Ð²Ñ‹Ðµ Ñ‚Ð¾Ñ€Ñ‚Ñ‹', '#FFD700'),
                ('kleingebaeck', 'ÐœÐµÐ»Ð¾Ñ‡ÑŒ', 'ÐžÑÐ½Ð¾Ð²Ð½Ð¾Ð¹ Ñ†ÐµÑ…', 'ÐœÐµÐ»ÐºÐ°Ñ Ð²Ñ‹Ð¿ÐµÑ‡ÐºÐ°', '#98FB98'),
                ('sand', 'ÐŸÐµÑÐ¾Ñ‡Ð½Ð¾Ðµ', 'ÐžÑÐ½Ð¾Ð²Ð½Ð¾Ð¹ Ñ†ÐµÑ…', 'ÐŸÐµÑÐ¾Ñ‡Ð½Ñ‹Ðµ Ñ‚Ð¾Ñ€Ñ‚Ñ‹', '#F0E68C'),
                ('napoleon', 'ÐÐ°Ð¿Ð¾Ð»ÐµÐ¾Ð½', 'ÐžÑÐ½Ð¾Ð²Ð½Ð¾Ð¹ Ñ†ÐµÑ…', 'Ð¡Ð»Ð¾ÐµÐ½Ñ‹Ðµ Ñ‚Ð¾Ñ€Ñ‚Ñ‹', '#ADD8E6')
            ]
            for cat_id, cat_name, workshop, desc, color in default_categories:
                cursor.execute('''
                    INSERT INTO categories (category_id, category_name, workshop_name, description, color)
                    VALUES (?, ?, ?, ?, ?)
                ''', (cat_id, cat_name, workshop, desc, color))
            logger.info(f"Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¾ {len(default_categories)} ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¹ Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ")

         # ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ ÐºÐ¾Ð»Ð¾Ð½ÐºÑƒ total_value Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ orders
        try:
            cursor.execute("ALTER TABLE orders ADD COLUMN total_value REAL DEFAULT 0.0")
            logger.info("Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° total_value Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ orders")
        except:
            # ÐšÐ¾Ð»Ð¾Ð½ÐºÐ° ÑƒÐ¶Ðµ ÐµÑÑ‚ÑŒ
            pass

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: Ð”ÐžÐ‘ÐÐ’Ð›Ð•ÐÐ˜Ð• Ð›ÐžÐ“Ð˜Ð¡Ð¢Ð˜ÐšÐ˜ ÐŸÐž Ð¦Ð•ÐÐ• ---
        try:
            # 1. Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ ÑÑƒÐ¼Ð¼Ñƒ Ð·Ð°ÐºÐ°Ð·Ð°
            cursor.execute("ALTER TABLE orders ADD COLUMN total_value REAL DEFAULT 0.0")
            logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° total_value Ð² orders")
        except: pass

        try:
            # 2. Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð° Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð¾Ð² Ð´Ð»Ñ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
            # Ð¤Ð¾Ñ€Ð¼Ð°Ñ‚ JSON: [{"limit": 300, "route_id": "route_b"}, {"limit": 0, "route_id": "route_a"}]
            cursor.execute("ALTER TABLE client_routes ADD COLUMN route_rules TEXT")
            logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° route_rules Ð² client_routes")
        except: pass

        # =========================================================================
        # ZUTATEN V2: Ð¡Ð¸ÑÑ‚ÐµÐ¼Ð° ÑƒÐ¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ñ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð°Ð¼Ð¸ (LMIV EU 1169/2011)
        # Ð¯Ð·Ñ‹ÐºÐ¸: DE (Ð½ÐµÐ¼ÐµÑ†ÐºÐ¸Ð¹), NL (Ð½Ð¸Ð´ÐµÑ€Ð»Ð°Ð½Ð´ÑÐºÐ¸Ð¹), FR (Ñ„Ñ€Ð°Ð½Ñ†ÑƒÐ·ÑÐºÐ¸Ð¹)
        # =========================================================================

        # 1. Ð¡Ð¿Ñ€Ð°Ð²Ð¾Ñ‡Ð½Ð¸Ðº 14 Ð°Ð»Ð»ÐµÑ€Ð³ÐµÐ½Ð¾Ð² Ð•Ð¡ (Art. 21 LMIV)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS allergens_reference (
                allergen_id INTEGER PRIMARY KEY AUTOINCREMENT,
                allergen_code TEXT UNIQUE NOT NULL,
                name_de TEXT NOT NULL,
                name_nl TEXT NOT NULL,
                name_fr TEXT NOT NULL,
                description_de TEXT,
                sort_order INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        ''')

        # 2. Ð¡Ð¿Ñ€Ð°Ð²Ð¾Ñ‡Ð½Ð¸Ðº Ñ„ÑƒÐ½ÐºÑ†Ð¸Ð¾Ð½Ð°Ð»ÑŒÐ½Ñ‹Ñ… ÐºÐ»Ð°ÑÑÐ¾Ð² Ð´Ð¾Ð±Ð°Ð²Ð¾Ðº (Annex VII Part C)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS additive_classes (
                class_id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_code TEXT UNIQUE NOT NULL,
                name_de TEXT NOT NULL,
                name_nl TEXT NOT NULL,
                name_fr TEXT NOT NULL,
                example_e_numbers TEXT,
                sort_order INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        ''')

        # 3. ÐœÐ°ÑÑ‚ÐµÑ€-Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð²
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ingredients_master (
                ingredient_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ingredient_code TEXT UNIQUE NOT NULL,
                name_de TEXT NOT NULL,
                name_nl TEXT,
                name_fr TEXT,
                category TEXT,
                is_compound INTEGER DEFAULT 0,
                expand_sub_ingredients_only INTEGER DEFAULT 0,
                compound_total_grams REAL,
                allergen_id INTEGER,
                allergen_ids TEXT,
                additive_class_id INTEGER,
                e_number TEXT,
                is_nano INTEGER DEFAULT 0,
                is_oil_fat INTEGER DEFAULT 0,
                botanical_origin_de TEXT,
                botanical_origin_nl TEXT,
                botanical_origin_fr TEXT,
                hydrogenation TEXT DEFAULT 'NONE',
                is_added_water INTEGER DEFAULT 0,
                loss_factor REAL DEFAULT 0.0,
                kcal_per_100g REAL,
                fat_per_100g REAL,
                carbs_per_100g REAL,
                protein_per_100g REAL,
                salt_per_100g REAL,
                notes TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (allergen_id) REFERENCES allergens_reference(allergen_id) ON DELETE SET NULL,
                FOREIGN KEY (additive_class_id) REFERENCES additive_classes(class_id) ON DELETE SET NULL
            )
        ''')

        # 4. Ð¡ÑƒÐ±-Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ñ‹ Ð´Ð»Ñ ÑÐ¾ÑÑ‚Ð°Ð²Ð½Ñ‹Ñ… Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð¾Ð² (Annex VII Part E)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ingredient_sub_ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_ingredient_id INTEGER NOT NULL,
                child_ingredient_id INTEGER NOT NULL,
                weight_percentage REAL NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (parent_ingredient_id) REFERENCES ingredients_master(ingredient_id) ON DELETE CASCADE,
                FOREIGN KEY (child_ingredient_id) REFERENCES ingredients_master(ingredient_id) ON DELETE RESTRICT,
                UNIQUE(parent_ingredient_id, child_ingredient_id)
            )
        ''')

        # 5. Ð¡Ð²ÑÐ·ÑŒ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² Ñ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð°Ð¼Ð¸
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recipe_ingredients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_nr TEXT NOT NULL,
                ingredient_id INTEGER NOT NULL,
                weight_grams REAL NOT NULL,
                highlight_quid INTEGER DEFAULT 0,
                sort_override INTEGER,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (article_nr) REFERENCES recipes(article_nr) ON DELETE CASCADE,
                FOREIGN KEY (ingredient_id) REFERENCES ingredients_master(ingredient_id) ON DELETE RESTRICT,
                UNIQUE(article_nr, ingredient_id)
            )
        ''')

        # Ð˜Ð½Ð´ÐµÐºÑÑ‹ Ð´Ð»Ñ zutaten_v2
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ingredients_allergen ON ingredients_master(allergen_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ingredients_additive ON ingredients_master(additive_class_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ingredients_category ON ingredients_master(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ingredients_code ON ingredients_master(ingredient_code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ingredients_active ON ingredients_master(active)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sub_ingredients_parent ON ingredient_sub_ingredients(parent_ingredient_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sub_ingredients_child ON ingredient_sub_ingredients(child_ingredient_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_article ON recipe_ingredients(article_nr)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_ingredient ON recipe_ingredients(ingredient_id)')

        # Ð—Ð°Ð¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ðµ Ð°Ð»Ð»ÐµÑ€Ð³ÐµÐ½Ð¾Ð² Ð•Ð¡ (ÐµÑÐ»Ð¸ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¿ÑƒÑÑ‚Ð°Ñ)
        cursor.execute("SELECT COUNT(*) FROM allergens_reference")
        if cursor.fetchone()[0] == 0:
            allergens_data = [
                ('GLUTEN', 'Gluten', 'Gluten', 'Gluten', 'Glutenhaltiges Getreide: Weizen, Roggen, Gerste, Hafer, Dinkel, Kamut', 1),
                ('CRUSTACEANS', 'Krebstiere', 'Schaaldieren', 'CrustacÃ©s', 'Krebstiere und daraus gewonnene Erzeugnisse', 2),
                ('EGGS', 'Eier', 'Eieren', 'Å’ufs', 'Eier und daraus gewonnene Erzeugnisse', 3),
                ('FISH', 'Fisch', 'Vis', 'Poisson', 'Fisch und daraus gewonnene Erzeugnisse', 4),
                ('PEANUTS', 'ErdnÃ¼sse', "Pinda's", 'Arachides', 'ErdnÃ¼sse und daraus gewonnene Erzeugnisse', 5),
                ('SOYBEANS', 'Soja', 'Soja', 'Soja', 'Sojabohnen und daraus gewonnene Erzeugnisse', 6),
                ('MILK', 'Milch', 'Melk', 'Lait', 'Milch und daraus gewonnene Erzeugnisse (einschlieÃŸlich Laktose)', 7),
                ('NUTS', 'SchalenfrÃ¼chte', 'Noten', 'Fruits Ã  coque', 'Mandeln, HaselnÃ¼sse, WalnÃ¼sse, CashewnÃ¼sse, PecannÃ¼sse, ParanÃ¼sse, Pistazien, Macadamia', 8),
                ('CELERY', 'Sellerie', 'Selderij', 'CÃ©leri', 'Sellerie und daraus gewonnene Erzeugnisse', 9),
                ('MUSTARD', 'Senf', 'Mosterd', 'Moutarde', 'Senf und daraus gewonnene Erzeugnisse', 10),
                ('SESAME', 'Sesam', 'Sesamzaad', 'SÃ©same', 'Sesamsamen und daraus gewonnene Erzeugnisse', 11),
                ('SULPHITES', 'Schwefeldioxid und Sulphite', 'Zwaveldioxide en sulfieten', 'Anhydride sulfureux et sulfites', 'Konzentrationen von mehr als 10 mg/kg oder 10 mg/l', 12),
                ('LUPIN', 'Lupinen', 'Lupine', 'Lupin', 'Lupinen und daraus gewonnene Erzeugnisse', 13),
                ('MOLLUSCS', 'Weichtiere', 'Weekdieren', 'Mollusques', 'Weichtiere und daraus gewonnene Erzeugnisse', 14),
            ]
            for code, de, nl, fr, desc, sort in allergens_data:
                cursor.execute('''
                    INSERT INTO allergens_reference (allergen_code, name_de, name_nl, name_fr, description_de, sort_order, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ''', (code, de, nl, fr, desc, sort, datetime.now().isoformat()))
            logger.info("Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¾ 14 Ð°Ð»Ð»ÐµÑ€Ð³ÐµÐ½Ð¾Ð² Ð•Ð¡")

        # Ð—Ð°Ð¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ðµ ÐºÐ»Ð°ÑÑÐ¾Ð² Ð´Ð¾Ð±Ð°Ð²Ð¾Ðº (ÐµÑÐ»Ð¸ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¿ÑƒÑÑ‚Ð°Ñ)
        cursor.execute("SELECT COUNT(*) FROM additive_classes")
        if cursor.fetchone()[0] == 0:
            additive_data = [
                ('PRESERVATIVE', 'Konservierungsstoff', 'Conserveringsmiddel', 'Conservateur', 'E 200-E 299', 1),
                ('ANTIOXIDANT', 'Antioxidationsmittel', 'Antioxidant', 'Antioxydant', 'E 300-E 399', 2),
                ('EMULSIFIER', 'Emulgator', 'Emulgator', 'Ã‰mulsifiant', 'E 322, E 471-E 495', 3),
                ('STABILIZER', 'Stabilisator', 'Stabilisator', 'Stabilisant', 'E 400-E 499', 4),
                ('THICKENER', 'Verdickungsmittel', 'Verdikkingsmiddel', 'Ã‰paississant', 'E 400-E 499', 5),
                ('GELLING_AGENT', 'Geliermittel', 'Geleermiddel', 'GÃ©lifiant', 'E 400-E 499', 6),
                ('COLORANT', 'Farbstoff', 'Kleurstof', 'Colorant', 'E 100-E 199', 7),
                ('SWEETENER', 'SÃ¼ÃŸungsmittel', 'Zoetstof', 'Ã‰dulcorant', 'E 950-E 969', 8),
                ('ACIDIFIER', 'SÃ¤uerungsmittel', 'Zuurteregelaar', 'Acidifiant', 'E 260, E 270, E 330', 9),
                ('RAISING_AGENT', 'Backtriebmittel', 'Rijsmiddel', 'Poudre Ã  lever', 'E 500, E 503', 10),
                ('FLAVOR_ENHANCER', 'GeschmacksverstÃ¤rker', 'Smaakversterker', 'Exhausteur de goÃ»t', 'E 620-E 640', 11),
                ('HUMECTANT', 'Feuchthaltemittel', 'Bevochtigingsmiddel', 'Humectant', 'E 420, E 422', 12),
                ('ANTI_CAKING', 'Trennmittel', 'Antiklontermiddel', 'AntiagglomÃ©rant', 'E 535, E 551, E 552', 13),
                ('GLAZING_AGENT', 'Ãœberzugsmittel', 'Glansmiddel', "Agent d'enrobage", 'E 901-E 904', 14),
                ('MODIFIED_STARCH', 'Modifizierte StÃ¤rke', 'Gemodificeerd zetmeel', 'Amidon modifiÃ©', 'E 1404-E 1450', 15),
            ]
            for code, de, nl, fr, examples, sort in additive_data:
                cursor.execute('''
                    INSERT INTO additive_classes (class_code, name_de, name_nl, name_fr, example_e_numbers, sort_order, active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ''', (code, de, nl, fr, examples, sort, datetime.now().isoformat()))
            logger.info("Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¾ 15 ÐºÐ»Ð°ÑÑÐ¾Ð² Ð´Ð¾Ð±Ð°Ð²Ð¾Ðº")

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: Ð”Ð¾Ð¿. Ð½ÑƒÑ‚Ñ€Ð¸ÐµÐ½Ñ‚Ñ‹ Ð² ingredients_master ---
        try:
            cursor.execute("PRAGMA table_info(ingredients_master)")
            ing_cols = [col[1] for col in cursor.fetchall()]

            for col_name in ['saturated_fat_per_100g', 'sugar_per_100g', 'kj_per_100g']:
                if col_name not in ing_cols:
                    logger.info(f"ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ {col_name} Ð² ingredients_master...")
                    cursor.execute(f"ALTER TABLE ingredients_master ADD COLUMN {col_name} REAL")
            if 'allergen_ids' not in ing_cols:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ allergen_ids Ð² ingredients_master...")
                cursor.execute("ALTER TABLE ingredients_master ADD COLUMN allergen_ids TEXT")
            if 'expand_sub_ingredients_only' not in ing_cols:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ expand_sub_ingredients_only Ð² ingredients_master...")
                cursor.execute("ALTER TABLE ingredients_master ADD COLUMN expand_sub_ingredients_only INTEGER DEFAULT 0")
            if 'compound_total_grams' not in ing_cols:
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÑÑŽ compound_total_grams Ð² ingredients_master...")
                cursor.execute("ALTER TABLE ingredients_master ADD COLUMN compound_total_grams REAL")
            conn.commit()
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ ingredients_master nutrition: {e}")

        # --- Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° label_settings (SPUREN Ð¸ Ð´Ñ€.) ---
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS label_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT,
                updated_at TEXT
            )
        ''')
        cursor.execute("SELECT COUNT(*) FROM label_settings")
        if cursor.fetchone()[0] == 0:
            now = datetime.now().isoformat()
            for key, val in [
                ('spuren_enabled', '1'),
                ('spuren_text_de', 'Kann Spuren von SchalenfrÃ¼chten, ErdnÃ¼ssen, Soja und Sesam enthalten.'),
            ]:
                cursor.execute(
                    "INSERT INTO label_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                    (key, val, now)
                )
            logger.info("Ð¡Ð¾Ð·Ð´Ð°Ð½Ð° Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° label_settings Ñ SPUREN Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ")
        conn.commit()

        # =========================================================================
        # ZUTATEN V2 â€” Ð ÐµÐºÑƒÑ€ÑÐ¸Ð²Ð½Ð¾Ðµ Ð´ÐµÑ€ÐµÐ²Ð¾ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² (Ð¼Ð½Ð¾Ð³Ð¾ÑƒÑ€Ð¾Ð²Ð½ÐµÐ²Ð°Ñ ÑÑ‚Ñ€ÑƒÐºÑ‚ÑƒÑ€Ð°)
        # =========================================================================

        # Ð”ÐµÑ€ÐµÐ²Ð¾ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð²: parent_article_nr -> child (recipe Ð¸Ð»Ð¸ ingredient)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS zutaten_v2_recipe_tree (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_article_nr TEXT NOT NULL,
                child_type TEXT NOT NULL CHECK(child_type IN ('recipe', 'ingredient')),
                child_article_nr TEXT,
                child_ingredient_id INTEGER,
                weight_grams REAL NOT NULL,
                loss_percent REAL DEFAULT 0.0,
                output_weight_grams REAL,
                highlight_quid INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (parent_article_nr) REFERENCES recipes(article_nr) ON DELETE CASCADE,
                FOREIGN KEY (child_article_nr) REFERENCES recipes(article_nr) ON DELETE RESTRICT,
                FOREIGN KEY (child_ingredient_id) REFERENCES ingredients_master(ingredient_id) ON DELETE RESTRICT,
                CHECK (
                    (child_type = 'recipe' AND child_article_nr IS NOT NULL AND child_ingredient_id IS NULL) OR
                    (child_type = 'ingredient' AND child_article_nr IS NULL AND child_ingredient_id IS NOT NULL)
                )
            )
        ''')

        # ÐŸÐ¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð½Ñ‹Ð¹ ÑÐ¾ÑÑ‚Ð°Ð² (Ñ€ÑƒÑ‡Ð½Ð°Ñ Ñ€ÐµÐ´Ð°ÐºÑ†Ð¸Ñ Ð´Ð»Ñ ÑÑ‚Ð¸ÐºÐµÑ‚ÐºÐ¸)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS zutaten_v2_confirmed_compositions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_nr TEXT UNIQUE NOT NULL,
                confirmed_text_de TEXT,
                confirmed_text_nl TEXT,
                confirmed_text_fr TEXT,
                auto_generated_text_de TEXT,
                recipe_hash TEXT,
                confirmed_by TEXT,
                confirmed_at TEXT,
                is_outdated INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (article_nr) REFERENCES recipes(article_nr) ON DELETE CASCADE
            )
        ''')

        # Ð˜Ð½Ð´ÐµÐºÑÑ‹ Ð´Ð»Ñ Ð½Ð¾Ð²Ñ‹Ñ… Ñ‚Ð°Ð±Ð»Ð¸Ñ†
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_zv2_tree_parent ON zutaten_v2_recipe_tree(parent_article_nr)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_zv2_tree_child_article ON zutaten_v2_recipe_tree(child_article_nr)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_zv2_tree_child_ingredient ON zutaten_v2_recipe_tree(child_ingredient_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_zv2_confirmed_article ON zutaten_v2_confirmed_compositions(article_nr)')

        conn.commit()

        # =========================================================================
        # MONOLITH API: Ð¢Ð°Ð±Ð»Ð¸Ñ†Ñ‹ Ð¸ Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ Ð´Ð»Ñ Ð¸Ð½Ñ‚ÐµÐ³Ñ€Ð°Ñ†Ð¸Ð¸ Ñ API Monolith
        # =========================================================================

        # Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¼Ð°Ð¿Ð¿Ð¸Ð½Ð³Ð° Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Monolith -> WISO
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS article_mapping (
                monolith_article_nr TEXT PRIMARY KEY,
                wiso_article_nr TEXT NOT NULL,
                monolith_name TEXT,
                unit_price REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: monolith_client_id Ð² client_routes ---
        try:
            cursor.execute("PRAGMA table_info(client_routes)")
            cols = [col[1] for col in cursor.fetchall()]
            if 'monolith_client_id' not in cols:
                cursor.execute("ALTER TABLE client_routes ADD COLUMN monolith_client_id TEXT")
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° monolith_client_id Ð² client_routes")
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ monolith_client_id: {e}")

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: unit_price Ð² recipes ---
        try:
            cursor.execute("PRAGMA table_info(recipes)")
            cols = [col[1] for col in cursor.fetchall()]
            if 'unit_price' not in cols:
                cursor.execute("ALTER TABLE recipes ADD COLUMN unit_price REAL DEFAULT 0.0")
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° unit_price Ð² recipes")
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ unit_price Ð² recipes: {e}")

        # --- ÐœÐ˜Ð“Ð ÐÐ¦Ð˜Ð¯: is_api_new Ð² orders ---
        try:
            cursor.execute("PRAGMA table_info(orders)")
            cols = [col[1] for col in cursor.fetchall()]
            if 'is_api_new' not in cols:
                cursor.execute("ALTER TABLE orders ADD COLUMN is_api_new INTEGER DEFAULT 0")
                logger.info("ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ¾Ð»Ð¾Ð½ÐºÐ° is_api_new Ð² orders")
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ is_api_new: {e}")

        conn.commit()

        # =========================================================================
        # Ð›Ð•Ð§Ð•ÐÐ˜Ð• Ð”Ð£Ð‘Ð›Ð˜ÐšÐÐ¢ÐžÐ’ (Ð—ÐÐŸÐ£Ð¡Ð¢Ð˜Ð¢Ð¬ ÐžÐ”Ð˜Ð Ð ÐÐ—)
        # =========================================================================
        try:
            # 1. Ð›ÐµÑ‡Ð¸Ð¼ Ð¾Ñ‚Ñ‡ÐµÑ‚Ñ‹ ÑÐºÐ»Ð°Ð´Ð° (daily_stock_reports)
            # ÐŸÐµÑ€ÐµÑÐ¾Ð·Ð´Ð°ÐµÐ¼ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ Ñ UNIQUE(date, article_nr)
            cursor.execute("CREATE TABLE IF NOT EXISTS daily_stock_reports_new (report_id INTEGER PRIMARY KEY, date TEXT, article_nr TEXT, quantity REAL, last_editor TEXT, created_at TEXT, updated_at TEXT, UNIQUE(date, article_nr))")
            
            # ÐŸÐµÑ€ÐµÐ½Ð¾ÑÐ¸Ð¼ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ
            cursor.execute("""
                INSERT OR REPLACE INTO daily_stock_reports_new (date, article_nr, quantity, last_editor, updated_at)
                SELECT date, article_nr, quantity, last_editor, updated_at 
                FROM daily_stock_reports 
                GROUP BY date, article_nr 
                ORDER BY updated_at DESC
            """)
            
            cursor.execute("DROP TABLE daily_stock_reports")
            cursor.execute("ALTER TABLE daily_stock_reports_new RENAME TO daily_stock_reports")
            logger.info("âœ… Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¾Ñ‚Ñ‡ÐµÑ‚Ð¾Ð² ÑÐºÐ»Ð°Ð´Ð° Ð²Ñ‹Ð»ÐµÑ‡ÐµÐ½Ð° (Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹ ÑƒÐ´Ð°Ð»ÐµÐ½Ñ‹).")

            # 2. Ð›ÐµÑ‡Ð¸Ð¼ ÑÐ±Ð¾Ñ€ÐºÑƒ Ð·Ð°ÐºÐ°Ð·Ð¾Ð² (order_picking)
            # Ð§Ñ‚Ð¾Ð±Ñ‹ Ð½Ðµ Ð²Ð¸ÑÐµÐ»Ð¸ "Ð¶ÐµÐ»Ñ‚Ñ‹Ðµ" Ð·Ð°ÐºÐ°Ð·Ñ‹
            cursor.execute("CREATE TABLE IF NOT EXISTS order_picking_new (picking_id INTEGER PRIMARY KEY, order_id TEXT, artikel_nr TEXT, pos INTEGER, total_qty INTEGER, picked_qty INTEGER, checked BOOLEAN, updated_at TEXT, UNIQUE(order_id, artikel_nr))")
            
            cursor.execute("""
                INSERT OR REPLACE INTO order_picking_new (order_id, artikel_nr, pos, total_qty, picked_qty, checked, updated_at)
                SELECT order_id, artikel_nr, pos, total_qty, picked_qty, checked, updated_at
                FROM order_picking
                GROUP BY order_id, artikel_nr
            """)
            
            cursor.execute("DROP TABLE order_picking")
            cursor.execute("ALTER TABLE order_picking_new RENAME TO order_picking")
            logger.info("âœ… Ð¢Ð°Ð±Ð»Ð¸Ñ†Ð° ÑÐ±Ð¾Ñ€ÐºÐ¸ Ð²Ñ‹Ð»ÐµÑ‡ÐµÐ½Ð°.")

        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð»ÐµÑ‡ÐµÐ½Ð¸Ñ Ð±Ð°Ð·Ñ‹: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
        # =========================================================================

        try:
            conn.commit()
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° final commit init_database: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
        conn.close()

        # Ð’Ñ‹Ð¿Ð¾Ð»Ð½ÑÐµÐ¼ Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ Ð¿Ð¾ÑÐ»Ðµ Ð¸Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ð¸
        self.migrate_logistics_tables()

    def migrate_logistics_tables(self):
        """ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ ÑÑ‚Ð°Ñ€Ð¾Ð¹ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ logistics_rules Ð½Ð° Ð½Ð¾Ð²Ñ‹Ðµ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ logistics_routes Ð¸ client_routes"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼, ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÐµÑ‚ Ð»Ð¸ ÑÑ‚Ð°Ñ€Ð°Ñ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° logistics_rules
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='logistics_rules'")
            old_table_exists = cursor.fetchone() is not None

            if old_table_exists:
                logger.info("ÐÐ°Ð¹Ð´ÐµÐ½Ð° ÑÑ‚Ð°Ñ€Ð°Ñ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° logistics_rules, Ð²Ñ‹Ð¿Ð¾Ð»Ð½ÑÐµÐ¼ Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸ÑŽ...")

                # Ð£Ð´Ð°Ð»ÑÐµÐ¼ ÑÑ‚Ð°Ñ€ÑƒÑŽ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ (Ð½Ð¾Ð²Ñ‹Ðµ ÑƒÐ¶Ðµ ÑÐ¾Ð·Ð´Ð°Ð½Ñ‹ Ð² init_database)
                cursor.execute("DROP TABLE IF EXISTS logistics_rules")
                conn.commit()
                logger.info("Ð¡Ñ‚Ð°Ñ€Ð°Ñ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° logistics_rules ÑƒÐ´Ð°Ð»ÐµÐ½Ð°")

                # Ð”Ð°Ð½Ð½Ñ‹Ðµ Ð±ÑƒÐ´ÑƒÑ‚ Ð¸Ð¼Ð¿Ð¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ñ‹ Ð¸Ð· CSV Ð¿Ñ€Ð¸ Ð·Ð°Ð¿ÑƒÑÐºÐµ ÑÐµÑ€Ð²ÐµÑ€Ð°

        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ñ€Ð¸ Ð¼Ð¸Ð³Ñ€Ð°Ñ†Ð¸Ð¸ Ñ‚Ð°Ð±Ð»Ð¸Ñ† Ð»Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÐ¸: {e}")
            conn.rollback()
        finally:
            conn.close()

    # ============================================
    # ÐŸÐžÐ›Ð¬Ð—ÐžÐ’ÐÐ¢Ð•Ð›Ð˜
    # ============================================
    def authenticate_user(self, username: str, password: str) -> Optional[object]:
        """ÐÑƒÑ‚ÐµÐ½Ñ‚Ð¸Ñ„Ð¸ÐºÐ°Ñ†Ð¸Ñ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ"""
        conn = self.get_connection()
        cursor = conn.cursor()

        password_hash = hashlib.sha256(password.encode()).hexdigest()

        cursor.execute('''
            SELECT * FROM users WHERE username = ? AND password_hash = ?
        ''', (username, password_hash))

        row = cursor.fetchone()
        if row:
            # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ Ð²Ñ€ÐµÐ¼Ñ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÐµÐ³Ð¾ Ð²Ñ…Ð¾Ð´Ð°
            cursor.execute('''
                UPDATE users SET last_login = ? WHERE user_id = ?
            ''', (datetime.now().isoformat(), row['user_id']))
            conn.commit()

            # Ð‘ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾Ðµ Ð¿Ð¾Ð»ÑƒÑ‡ÐµÐ½Ð¸Ðµ permissions (Ð¼Ð¾Ð¶ÐµÑ‚ Ð¾Ñ‚ÑÑƒÑ‚ÑÑ‚Ð²Ð¾Ð²Ð°Ñ‚ÑŒ Ð² ÑÑ‚Ð°Ñ€Ñ‹Ñ… Ð‘Ð”)
            try:
                permissions = row['permissions'] or ''
            except (KeyError, IndexError):
                permissions = ''

            # Ð’Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÐ¼ Ð¾Ð±ÑŠÐµÐºÑ‚ User
            user = User(
                user_id=row['user_id'],
                username=row['username'],
                password_hash=row['password_hash'],
                role=row['role'],
                warehouse_id=row['warehouse_id'],
                created_at=row['created_at'],
                last_login=row['last_login'],
                permissions=permissions,
                first_name=row['first_name'] if 'first_name' in row.keys() else '',
                last_name=row['last_name'] if 'last_name' in row.keys() else '',
                display_name=(
                    row['display_name'] if 'display_name' in row.keys() and row['display_name']
                    else self.format_user_display_name(
                        row['first_name'] if 'first_name' in row.keys() else '',
                        row['last_name'] if 'last_name' in row.keys() else '',
                        row['username']
                    )
                )
            )
            conn.close()
            return user

        conn.close()
        return None

    def create_user(self, username, password, role, warehouse_id, permissions, first_name=None, last_name=None):
        """Ð¡Ð¾Ð·Ð´Ð°Ñ‚ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ (Ð¡ ÐŸÐ ÐÐ’ÐÐœÐ˜)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            display_name = self.format_user_display_name(first_name, last_name, username)
            cursor.execute('''
                INSERT INTO users (username, password_hash, role, warehouse_id, permissions, first_name, last_name, display_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                username, password_hash, role, warehouse_id, permissions,
                str(first_name or '').strip() or None,
                str(last_name or '').strip() or None,
                display_name,
                datetime.now().isoformat()
            ))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def delete_user(self, user_id: int) -> bool:
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()
        return deleted

    def update_user(self, user_id, username=None, password=None, role=None, warehouse_id=None, permissions=None, first_name=None, last_name=None):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ (Ð¡ ÐŸÐ ÐÐ’ÐÐœÐ˜)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            updates = []
            params = []

            if username:
                updates.append("username=?")
                params.append(username)
            if password:
                updates.append("password_hash=?")
                params.append(hashlib.sha256(password.encode()).hexdigest())
            if role:
                updates.append("role=?")
                params.append(role)
            if warehouse_id is not None: # ÐœÐ¾Ð¶ÐµÑ‚ Ð±Ñ‹Ñ‚ÑŒ Ð¿ÑƒÑÑ‚Ð¾Ð¹ ÑÑ‚Ñ€Ð¾ÐºÐ¾Ð¹
                updates.append("warehouse_id=?")
                params.append(warehouse_id)
            if permissions is not None:
                updates.append("permissions=?")
                params.append(permissions)
            if first_name is not None:
                updates.append("first_name=?")
                params.append(str(first_name).strip() or None)
            if last_name is not None:
                updates.append("last_name=?")
                params.append(str(last_name).strip() or None)

            # If any display-related field changes, recompute display_name.
            if username is not None or first_name is not None or last_name is not None:
                row = cursor.execute(
                    "SELECT username, first_name, last_name FROM users WHERE user_id = ?",
                    (user_id,)
                ).fetchone()
                if row:
                    new_username = username if username is not None else row['username']
                    new_first = first_name if first_name is not None else row['first_name']
                    new_last = last_name if last_name is not None else row['last_name']
                    updates.append("display_name=?")
                    params.append(self.format_user_display_name(new_first, new_last, new_username))

            if not updates: return False

            params.append(user_id)
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id=?", params)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Update user error: {e}")
            return False
        finally:
            conn.close()

    def get_all_users(self) -> list:
        """Get all users."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
            rows = cursor.fetchall()

            users = []
            for row in rows:
                users.append({
                    'user_id': row['user_id'],
                    'username': row['username'],
                    'first_name': row['first_name'] if 'first_name' in row.keys() else '',
                    'last_name': row['last_name'] if 'last_name' in row.keys() else '',
                    'display_name': (
                        row['display_name'] if 'display_name' in row.keys() and row['display_name']
                        else self.format_user_display_name(
                            row['first_name'] if 'first_name' in row.keys() else '',
                            row['last_name'] if 'last_name' in row.keys() else '',
                            row['username']
                        )
                    ),
                    'role': row['role'] if 'role' in row.keys() else '',
                    'warehouse_id': row['warehouse_id'] if 'warehouse_id' in row.keys() else None,
                    'created_at': row['created_at'] if 'created_at' in row.keys() else '',
                    'last_login': row['last_login'] if 'last_login' in row.keys() else None,
                    'permissions': row['permissions'] if 'permissions' in row.keys() else ''
                })
            return users
        finally:
            conn.close()

    # ============================================
    # ÐšÐÐ¢Ð•Ð“ÐžÐ Ð˜Ð˜ (Ð¦Ð•Ð¥Ð)
    # ============================================
    def get_all_categories(self) -> list:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð²ÑÐµ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¸/Ñ†ÐµÑ…Ð° Ð¢ÐžÐ›Ð¬ÐšÐž Ð¸Ð· Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ categories"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¸ Ð¢ÐžÐ›Ð¬ÐšÐž Ð¸Ð· Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ categories (Ð½Ðµ Ð¸Ð· Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð²!)
        # Ð­Ñ‚Ð¾ Ð¿Ð¾Ð·Ð²Ð¾Ð»ÑÐµÑ‚ ÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ð¾ ÑƒÐ´Ð°Ð»ÑÑ‚ÑŒ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¸
        cursor.execute('''
            SELECT id, category_id, category_name, workshop_name, description, color, active
            FROM categories
            ORDER BY category_name
        ''')
        category_rows = cursor.fetchall()

        categories = []
        for row in category_rows:
            categories.append({
                'id': row['id'],
                'category_id': row['category_id'],
                'category_name': row['category_name'],
                'workshop_name': row['workshop_name'] or '',
                'description': row['description'] or '',
                'color': row['color'] or '#95a5a6',
                'active': row['active']
            })

        conn.close()

        return categories

    def get_category_names(self) -> list:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð½Ð°Ð·Ð²Ð°Ð½Ð¸Ñ Ð°ÐºÑ‚Ð¸Ð²Ð½Ñ‹Ñ… ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¹ Ð¸Ð· Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ categories"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð¸Ð· Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ categories (ÑƒÐ¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼Ñ‹Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº)
        cursor.execute('SELECT category_name FROM categories WHERE active = 1 ORDER BY category_name')
        names = [row['category_name'] for row in cursor.fetchall() if row['category_name']]

        conn.close()
        return names

    def add_category(self, category_id: str, category_name: str, workshop_name: str = '',
                    description: str = '', color: str = '#95a5a6') -> bool:
        """Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð½Ð¾Ð²ÑƒÑŽ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸ÑŽ"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO categories (category_id, category_name, workshop_name, description, color, active)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (category_id, category_name, workshop_name or category_name, description, color))

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding category: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def update_category(self, category_id: str, category_name: str, workshop_name: str = '',
                       description: str = '', color: str = '#95a5a6', active: int = 1) -> bool:
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸ÑŽ"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE categories
                SET category_name = ?, workshop_name = ?, description = ?,
                    color = ?, active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE category_id = ?
            ''', (category_name, workshop_name or category_name, description, color, active, category_id))

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating category: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def delete_category(self, category_id: str) -> bool:
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸ÑŽ (Ñ‚Ð¾Ð»ÑŒÐºÐ¾ ÐµÑÐ»Ð¸ Ð½ÐµÑ‚ ÑÐ²ÑÐ·Ð°Ð½Ð½Ñ‹Ñ… Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð²)"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Ð¡Ð½Ð°Ñ‡Ð°Ð»Ð° Ð¿Ð¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð½Ð°Ð·Ð²Ð°Ð½Ð¸Ðµ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¸ Ð´Ð»Ñ Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÐ¸ Ð² recipes
            cursor.execute('SELECT category_name FROM categories WHERE category_id = ?', (category_id,))
            row = cursor.fetchone()
            if not row:
                logger.warning(f"Category not found: {category_id}")
                return False

            category_name = row['category_name']

            # ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ, ÐµÑÑ‚ÑŒ Ð»Ð¸ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ñ‹ Ñ ÑÑ‚Ð¾Ð¹ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸ÐµÐ¹ (Ð¿Ð¾ Ð½Ð°Ð·Ð²Ð°Ð½Ð¸ÑŽ!)
            cursor.execute('SELECT COUNT(*) FROM recipes WHERE category = ?', (category_name,))
            count = cursor.fetchone()[0]

            if count > 0:
                logger.warning(f"Cannot delete category {category_id} ({category_name}): {count} recipes using it")
                return False

            # Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸ÑŽ
            cursor.execute('DELETE FROM categories WHERE category_id = ?', (category_id,))
            conn.commit()
            logger.info(f"Deleted category: {category_id} ({category_name})")
            return True
        except Exception as e:
            logger.error(f"Error deleting category: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    # ============================================
    # Ð—ÐÐšÐÐ—Ð«
    # ============================================
    def order_exists_by_lieferschein(self, lieferschein_nr: str) -> bool:
        """
        ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ, ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÐµÑ‚ Ð»Ð¸ Ð·Ð°ÐºÐ°Ð· Ñ Ð´Ð°Ð½Ð½Ñ‹Ð¼ Ð½Ð¾Ð¼ÐµÑ€Ð¾Ð¼ Lieferschein Ð¡Ð•Ð“ÐžÐ”ÐÐ¯
        ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ ÑÐµÐ³Ð¾Ð´Ð½ÑÑˆÐ½Ð¸Ðµ Ð·Ð°ÐºÐ°Ð·Ñ‹ - ÑÑ‚Ð°Ñ€Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ð¼Ð¾Ð¶Ð½Ð¾ Ð¿ÐµÑ€ÐµÐ·Ð°Ð³Ñ€ÑƒÐ¶Ð°Ñ‚ÑŒ
        """
        from datetime import datetime

        conn = self.get_connection()
        cursor = conn.cursor()

        # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ ÑÐµÐ³Ð¾Ð´Ð½ÑÑˆÐ½ÑŽÑŽ Ð´Ð°Ñ‚Ñƒ Ð² Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ðµ YYYY-MM-DD
        today_str = datetime.now().strftime('%Y-%m-%d')

        cursor.execute('''
            SELECT COUNT(*) FROM orders
            WHERE order_id LIKE ?
            AND created_at LIKE ?
        ''', (f'LS-{lieferschein_nr}%', f'{today_str}%'))

        count = cursor.fetchone()[0]
        conn.close()
        return count > 0

    @staticmethod
    def _normalize_kunde(k: str) -> str:
        """ÐÐ¾Ñ€Ð¼Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ñ Ð¸Ð¼ÐµÐ½Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð° Ð´Ð»Ñ ÑÑ€Ð°Ð²Ð½ÐµÐ½Ð¸Ñ (Mix Markt 027 == Mix Markt 27)."""
        import re as _re
        k = k.lower().strip()
        for s in ['gmbh', 'ohg', 'e.k.', 'inh.', 'gbr']:
            k = k.replace(s, '')
        m = _re.search(r'mix\s*markt\s*0*(\d+)', k)
        if m:
            return 'mixmarkt_' + m.group(1)
        return _re.sub(r'\s+', ' ', k).strip()

    def order_exists(self, order_id: str, order_data: dict = None) -> bool:
        """
        ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ, ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÐµÑ‚ Ð»Ð¸ Ð·Ð°ÐºÐ°Ð· Ð² Ð±Ð°Ð·Ðµ.
        1. Ð¢Ð¾Ñ‡Ð½Ð¾Ðµ ÑÐ¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ Ð¿Ð¾ order_id
        2. Ð¡Ð¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ Ð¿Ð¾ Ð¾Ñ‡Ð¸Ñ‰ÐµÐ½Ð½Ð¾Ð¼Ñƒ auftrag_nr (Ð±ÐµÐ· Ð¿Ñ€Ð¾Ð±ÐµÐ»Ð¾Ð²)
        3. Ð•ÑÐ»Ð¸ Ð¿ÐµÑ€ÐµÐ´Ð°Ð½ order_data â€” ÐºÑ€Ð¾ÑÑ-Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÐ° ABâ†”MO Ð¿Ð¾ ÑÐ¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸ÑŽ ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ñ‹Ñ… Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð²
        """
        import re
        conn = self.get_connection()
        try:
            cursor = conn.cursor()

            # 1. Ð¢Ð¾Ñ‡Ð½Ð¾Ðµ ÑÐ¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ Ð¿Ð¾ order_id
            cursor.execute('SELECT 1 FROM orders WHERE order_id = ? LIMIT 1', (order_id,))
            if cursor.fetchone() is not None:
                return True

            # 2. Ð¡Ð¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ Ð¿Ð¾ Ð¾Ñ‡Ð¸Ñ‰ÐµÐ½Ð½Ð¾Ð¼Ñƒ auftrag_nr
            clean_nr = order_id.replace('AB-', '').replace('WS-', '').replace('MO-', '')
            clean_nr = re.sub(r'\s+', '', clean_nr).replace(',', '').replace('.', '')

            cursor.execute('SELECT order_id, order_data FROM orders WHERE delivery_date >= date("now", "-3 days")')
            rows = cursor.fetchall()
            for row in rows:
                existing_id, data_json = row
                try:
                    data = json.loads(data_json)
                    existing_nr = str(data.get('auftrag_nr', ''))
                    existing_clean = re.sub(r'\s+', '', existing_nr).replace(',', '').replace('.', '')
                    if existing_clean == clean_nr:
                        logger.info(f"[ORDER_EXISTS] ÐÐ°Ð¹Ð´ÐµÐ½ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚ Ð¿Ð¾ auftrag_nr: {order_id} == {existing_id}")
                        return True
                except:
                    continue

            # 3. ÐšÑ€Ð¾ÑÑ-Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÐ° ABâ†”MO Ð¿Ð¾ Ð¸Ð¼ÐµÐ½Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð° + ÑÐ¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸ÑŽ ÐšÐžÐÐšÐ Ð•Ð¢ÐÐ«Ð¥ Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð²
            # Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð¼ÐµÐ¶Ð´Ñƒ Ñ€Ð°Ð·Ð½Ñ‹Ð¼Ð¸ ÑÐ¸ÑÑ‚ÐµÐ¼Ð°Ð¼Ð¸: MO- vs AB-/WS- (Ð½Ðµ MO- vs MO-)
            if order_data:
                is_mo = order_id.startswith('MO-')
                is_ab = order_id.startswith('AB-') or order_id.startswith('WS-')
                new_kunde = self._normalize_kunde(order_data.get('kunde', ''))
                new_artikel = order_data.get('artikel', [])
                new_art_set = set()
                for a in new_artikel:
                    nr = str(a.get('artikel_nr', a.get('nummer', ''))).strip()
                    qty = str(a.get('menge', ''))
                    if nr:
                        new_art_set.add(f"{nr}:{qty}")

                if new_kunde and new_art_set:
                    for row in rows:
                        existing_id, data_json = row
                        try:
                            # Ð¢Ð¾Ð»ÑŒÐºÐ¾ ÐºÑ€Ð¾ÑÑ-ÑÐ¸ÑÑ‚ÐµÐ¼Ð°: MO Ð¿Ñ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ Ð¿Ñ€Ð¾Ñ‚Ð¸Ð² AB/WS Ð¸ Ð½Ð°Ð¾Ð±Ð¾Ñ€Ð¾Ñ‚
                            if is_mo and existing_id.startswith('MO-'):
                                continue
                            if is_ab and (existing_id.startswith('AB-') or existing_id.startswith('WS-')):
                                continue

                            data = json.loads(data_json)
                            ex_kunde = self._normalize_kunde(data.get('kunde', ''))
                            if ex_kunde != new_kunde:
                                continue

                            # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ ÑÐ¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ñ‹Ñ… Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð² (Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» + ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾)
                            ex_artikel = data.get('artikel', [])
                            ex_art_set = set()
                            for a in ex_artikel:
                                nr = str(a.get('artikel_nr', a.get('nummer', ''))).strip()
                                qty = str(a.get('menge', ''))
                                if nr:
                                    ex_art_set.add(f"{nr}:{qty}")

                            if ex_art_set and ex_art_set == new_art_set:
                                logger.info(f"[ORDER_EXISTS] ÐšÑ€Ð¾ÑÑ-Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚ ABâ†”MO: {order_id} ({new_kunde}) == {existing_id}")
                                return True
                        except:
                            continue

            return False
        finally:
            conn.close()

    def find_auftrag_by_kunde_date_artikel(self, kunden_nr: str, datum: str, artikel_list: list) -> Optional[str]:
        """
        Ð£Ð¼Ð½Ñ‹Ð¹ Ð¿Ð¾Ð¸ÑÐº Auftrag: Ð–ÐµÑÑ‚ÐºÐ¸Ð¹ Ñ„Ð¸Ð»ÑŒÑ‚Ñ€ Ð¿Ð¾ Kunden-Nr, Ð·Ð°Ñ‚ÐµÐ¼ Scoring Ð¿Ð¾ Ñ‚Ð¾Ð²Ð°Ñ€Ð°Ð¼
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            target_kunden = str(kunden_nr).strip()
            if not target_kunden:
                return None # Ð‘ÐµÐ· Ð½Ð¾Ð¼ÐµÑ€Ð° ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð° Ð¿Ð¾Ð¸ÑÐº Ð½ÐµÐ²Ð¾Ð·Ð¼Ð¾Ð¶ÐµÐ½

            # 1. ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ñ Ð¢ÐÐšÐ˜Ðœ Ð–Ð• Kunden-Nr
            # ÐœÑ‹ Ð½Ðµ Ñ„Ð¸Ð»ÑŒÑ‚Ñ€ÑƒÐµÐ¼ Ð¿Ð¾ Ð´Ð°Ñ‚Ðµ Ð¶ÐµÑÑ‚ÐºÐ¾, Ñ‚Ð°Ðº ÐºÐ°Ðº Ð´Ð°Ñ‚Ñ‹ ÑÑ‡ÐµÑ‚Ð° Ð¸ Ð·Ð°ÐºÐ°Ð·Ð° Ð¼Ð¾Ð³ÑƒÑ‚ Ð¾Ñ‚Ð»Ð¸Ñ‡Ð°Ñ‚ÑŒÑÑ Ð½Ð° 1-2 Ð´Ð½Ñ
            cursor.execute('''
                SELECT order_id, order_data
                FROM orders
                WHERE order_id LIKE 'AB-%'
            ''')

            candidates = []

            for row in cursor.fetchall():
                order_data = json.loads(row['order_data'])
                order_kunden = str(order_data.get('kunden_nr', '')).strip()

                # ÐÐ¾Ñ€Ð¼Ð°Ð»Ð¸Ð·ÑƒÐµÐ¼ Ð¾Ð±Ð° Ð½Ð¾Ð¼ÐµÑ€Ð° Ð´Ð»Ñ ÑÑ€Ð°Ð²Ð½ÐµÐ½Ð¸Ñ (ÑƒÐ±Ð¸Ñ€Ð°ÐµÐ¼ Ð²ÐµÐ´ÑƒÑ‰Ð¸Ðµ Ð½ÑƒÐ»Ð¸ Ð¸ Ð¿Ñ€Ð¾Ð±ÐµÐ»Ñ‹)
                order_kunden_normalized = order_kunden.lstrip('0') if order_kunden else ''
                target_kunden_normalized = target_kunden.lstrip('0') if target_kunden else ''

                # Ð–Ð•Ð¡Ð¢ÐšÐÐ¯ ÐŸÐ ÐžÐ’Ð•Ð ÐšÐ KUNDEN-NR (ÑÐ½Ð°Ñ‡Ð°Ð»Ð° Ñ‚Ð¾Ñ‡Ð½Ð¾Ðµ ÑÐ¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ, Ð¿Ð¾Ñ‚Ð¾Ð¼ Ð½Ð¾Ñ€Ð¼Ð°Ð»Ð¸Ð·Ð¾Ð²Ð°Ð½Ð½Ð¾Ðµ)
                if order_kunden == target_kunden or (order_kunden_normalized and order_kunden_normalized == target_kunden_normalized):
                    # Ð”Ð¾Ð¿Ð¾Ð»Ð½Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð°Ñ Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð¿Ð¾ Ð´Ð°Ñ‚Ðµ (Ð¾Ð¿Ñ†Ð¸Ð¾Ð½Ð°Ð»ÑŒÐ½Ð¾, Ð½Ð¾ Ð¿Ð¾Ð»ÐµÐ·Ð½Ð¾ Ð´Ð»Ñ Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð¾ÑÑ‚Ð¸)
                    # Ð•ÑÐ»Ð¸ Ð´Ð°Ñ‚Ñ‹ ÑÐ¸Ð»ÑŒÐ½Ð¾ Ð¾Ñ‚Ð»Ð¸Ñ‡Ð°ÑŽÑ‚ÑÑ (> 7 Ð´Ð½ÐµÐ¹), Ð¼Ð¾Ð¶Ð½Ð¾ Ð¿Ñ€Ð¾Ð¿ÑƒÑÐºÐ°Ñ‚ÑŒ, Ð½Ð¾ Ð¿Ð¾ÐºÐ° Ð±ÐµÑ€ÐµÐ¼ Ð²ÑÐµ
                    candidates.append((row['order_id'], order_data))
                    logger.debug(f"  âœ… Match: {row['order_id']} - kunden_nr: {order_kunden} (normalized: {order_kunden_normalized})")

            if not candidates:
                logger.info(f"âŒ Smart Match: No orders found for Kunden-Nr {target_kunden}")
                conn.close()
                return None

            logger.info(f"ðŸ”Ž Smart Match: Found {len(candidates)} candidates for Kunden-Nr {target_kunden}")

            # 2. ÐŸÐ¾Ð´Ð³Ð¾Ñ‚Ð¾Ð²ÐºÐ° Ð´Ð°Ð½Ð½Ñ‹Ñ… Ð¸Ð· ÑÑ‡ÐµÑ‚Ð°
            invoice_items = {}
            for art in artikel_list:
                key = str(art.get('nummer', art.get('artikel_nr', ''))).strip()
                try: qty = float(art.get('menge', 0))
                except: qty = 0
                if key: invoice_items[key] = invoice_items.get(key, 0) + qty

            # 3. Ð‘Ð°Ð»Ð»ÑŒÐ½Ð°Ñ Ð¾Ñ†ÐµÐ½ÐºÐ° (Scoring)
            best_match_id = None
            highest_score = 0

            for order_id, order_data in candidates:
                current_score = 0
                order_items = {}
                for item in order_data.get('artikel', []):
                    key = str(item.get('artikel_nr', item.get('nummer', ''))).strip()
                    try: qty = float(item.get('menge', 0))
                    except: qty = 0
                    if key: order_items[key] = order_items.get(key, 0) + qty

                # Ð¡Ñ€Ð°Ð²Ð½ÐµÐ½Ð¸Ðµ
                matches_found = 0
                for inv_sku, inv_qty in invoice_items.items():
                    if inv_sku in order_items:
                        ord_qty = order_items[inv_sku]
                        matches_found += 1
                        current_score += 10 # Ð¡Ð¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð°
                        if abs(inv_qty - ord_qty) < 0.01:
                            current_score += 20 # Ð¡Ð¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð°
                        else:
                            current_score += 5  # Ð Ð°Ð·Ð½Ð¾Ðµ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾
                    else:
                        current_score -= 5 # Ð›Ð¸ÑˆÐ½Ð¸Ð¹ Ñ‚Ð¾Ð²Ð°Ñ€ Ð² ÑÑ‡ÐµÑ‚Ðµ (ÑˆÑ‚Ñ€Ð°Ñ„)

                if current_score > highest_score:
                    highest_score = current_score
                    best_match_id = order_id

            conn.close()

            # 4. ÐŸÐ¾Ñ€Ð¾Ð³
            MIN_THRESHOLD = 20 # Ð”Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾ ÑÐ¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ñ 2-Ñ… Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Ð¸Ð»Ð¸ 1-Ð³Ð¾ Ñ Ñ‚Ð¾Ñ‡Ð½Ñ‹Ð¼ ÐºÐ¾Ð»-Ð²Ð¾Ð¼

            if highest_score >= MIN_THRESHOLD:
                logger.info(f"âœ… Smart Match WINNER: {best_match_id} (Score: {highest_score})")
                return best_match_id
            else:
                logger.warning(f"âš ï¸ Smart Match: Best score {highest_score} is too low for {target_kunden}")
                return None

        except Exception as e:
            logger.error(f"Error in Smart Matching: {e}")
            if conn: conn.close()
            return None

    def find_auftrag_by_kunde_name(self, kunde_name: str, datum: str, artikel_list: list) -> Optional[str]:
        """
        ÐÐ»ÑŒÑ‚ÐµÑ€Ð½Ð°Ñ‚Ð¸Ð²Ð½Ñ‹Ð¹ Ð¿Ð¾Ð¸ÑÐº Auftrag Ð¿Ð¾ Ð¸Ð¼ÐµÐ½Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð° (ÐºÐ¾Ð³Ð´Ð° kunden_nr Ð½ÐµÑ‚ Ð² Rechnung)
        Ð¡Ñ€Ð°Ð²Ð½Ð¸Ð²Ð°ÐµÐ¼ Ð¿Ð¾ Ð¸Ð¼ÐµÐ½Ð¸ + Ð´Ð°Ñ‚Ð° + Ñ‚Ð¾Ð²Ð°Ñ€Ñ‹
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            target_name = str(kunde_name).strip().lower()
            if not target_name:
                logger.warning("âŒ Search by name: kunde_name is empty")
                return None

            logger.info(f"ðŸ”Ž Searching Auftrag by name: '{kunde_name}' (date: {datum})")

            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð²ÑÐµ Ð·Ð°ÐºÐ°Ð·Ñ‹ AuftragsbestÃ¤tigung
            cursor.execute('''
                SELECT order_id, order_data
                FROM orders
                WHERE order_id LIKE 'AB-%'
            ''')

            candidates = []

            for row in cursor.fetchall():
                order_data = json.loads(row['order_data'])
                order_kunde = str(order_data.get('kunde', '')).strip().lower()

                # ÐÐµÑ‡ÐµÑ‚ÐºÐ¾Ðµ ÑÑ€Ð°Ð²Ð½ÐµÐ½Ð¸Ðµ Ð¸Ð¼ÐµÐ½Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð° (Ð¿Ñ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ Ð²Ñ…Ð¾Ð¶Ð´ÐµÐ½Ð¸Ðµ)
                # ÐÐ°Ð¿Ñ€Ð¸Ð¼ÐµÑ€: "Mix Markt 4301, Inh. Ilina Alona" ÑÐ¾Ð´ÐµÑ€Ð¶Ð¸Ñ‚ "Mix Markt 4301"
                if target_name in order_kunde or order_kunde in target_name:
                    candidates.append((row['order_id'], order_data))
                    logger.debug(f"  âœ… Name match: {row['order_id']} - kunde: {order_data.get('kunde')}")

            if not candidates:
                logger.info(f"âŒ Search by name: No orders found for '{kunde_name}'")
                conn.close()
                return None

            logger.info(f"ðŸ”Ž Search by name: Found {len(candidates)} candidates")

            # ÐŸÐ¾Ð´Ð³Ð¾Ñ‚Ð¾Ð²ÐºÐ° Ð´Ð°Ð½Ð½Ñ‹Ñ… Ð¸Ð· ÑÑ‡ÐµÑ‚Ð°
            invoice_items = {}
            for art in artikel_list:
                key = str(art.get('nummer', art.get('artikel_nr', ''))).strip()
                try: qty = float(art.get('menge', 0))
                except: qty = 0
                if key: invoice_items[key] = invoice_items.get(key, 0) + qty

            # Ð‘Ð°Ð»Ð»ÑŒÐ½Ð°Ñ Ð¾Ñ†ÐµÐ½ÐºÐ° (Scoring)
            best_match_id = None
            highest_score = 0

            for order_id, order_data in candidates:
                current_score = 0
                order_items = {}
                for item in order_data.get('artikel', []):
                    key = str(item.get('artikel_nr', item.get('nummer', ''))).strip()
                    try: qty = float(item.get('menge', 0))
                    except: qty = 0
                    if key: order_items[key] = order_items.get(key, 0) + qty

                # Ð¡Ñ€Ð°Ð²Ð½ÐµÐ½Ð¸Ðµ Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð²
                for inv_sku, inv_qty in invoice_items.items():
                    if inv_sku in order_items:
                        ord_qty = order_items[inv_sku]
                        current_score += 10  # Ð¡Ð¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð°
                        if abs(inv_qty - ord_qty) < 0.01:
                            current_score += 20  # Ð¡Ð¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð°
                        else:
                            current_score += 5   # Ð Ð°Ð·Ð½Ð¾Ðµ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾
                    else:
                        current_score -= 5  # Ð›Ð¸ÑˆÐ½Ð¸Ð¹ Ñ‚Ð¾Ð²Ð°Ñ€ Ð² ÑÑ‡ÐµÑ‚Ðµ (ÑˆÑ‚Ñ€Ð°Ñ„)

                logger.debug(f"  Score for {order_id}: {current_score}")

                if current_score > highest_score:
                    highest_score = current_score
                    best_match_id = order_id

            conn.close()

            # ÐŸÐ¾Ñ€Ð¾Ð³
            MIN_THRESHOLD = 20  # Ð”Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾ ÑÐ¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ñ 2-Ñ… Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Ð¸Ð»Ð¸ 1-Ð³Ð¾ Ñ Ñ‚Ð¾Ñ‡Ð½Ñ‹Ð¼ ÐºÐ¾Ð»-Ð²Ð¾Ð¼

            if highest_score >= MIN_THRESHOLD:
                logger.info(f"âœ… Search by name WINNER: {best_match_id} (Score: {highest_score})")
                return best_match_id
            else:
                logger.warning(f"âš ï¸ Search by name: Best score {highest_score} is too low for '{kunde_name}'")
                return None

        except Exception as e:
            logger.error(f"Error in search by name: {e}")
            if conn: conn.close()
            return None

    def create_order(self, order_id: str, order_data: dict, warehouse_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        # Ð’Ñ‹Ñ‚Ð°ÑÐºÐ¸Ð²Ð°ÐµÐ¼ Ð´Ð°Ñ‚Ñ‹ Ð¸Ð· ÑÐ»Ð¾Ð²Ð°Ñ€Ñ
        d_date = order_data.get('delivery_date')
        p_date = order_data.get('production_date')

        cursor.execute('''
            INSERT OR REPLACE INTO orders
            (order_id, order_data, status, warehouse_id, printed, delivery_date, production_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, json.dumps(order_data), 'pending', warehouse_id, 0, d_date, p_date, now, now))
        conn.commit()
        conn.close()

    def update_order(self, oid, updates):
        with self.get_connection() as conn:
            row = conn.execute("SELECT order_data, printed, boxes_count FROM orders WHERE order_id=?", (oid,)).fetchone()
            if row:
                data = json.loads(row['order_data'])
                data.update(updates)

                # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ Ð²ÑÐµ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸, Ð²ÐºÐ»ÑŽÑ‡Ð°Ñ Ð½Ð¾Ð²ÑƒÑŽ
                d_date = updates.get('delivery_date', data.get('delivery_date'))
                p_date = updates.get('production_date', data.get('production_date'))
                # ÐšÑ€Ð¸Ñ‚Ð¸Ñ‡Ð½Ð¾: ÐµÑÐ»Ð¸ printed Ð½Ðµ Ð¿Ñ€Ð¸ÑˆÐµÐ» Ð² updates, ÑÐ¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ñ‚ÐµÐºÑƒÑ‰ÐµÐµ Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ Ð¸Ð· ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ Ð‘Ð”,
                # Ð° Ð½Ðµ Ð¸Ð· JSON (Ñ‚Ð°Ð¼ Ð¼Ð¾Ð¶ÐµÑ‚ Ð±Ñ‹Ñ‚ÑŒ ÑƒÑÑ‚Ð°Ñ€ÐµÐ²ÑˆÐµÐµ False).
                current_printed = bool(row['printed']) if 'printed' in row.keys() else bool(data.get('printed', False))
                printed = 1 if updates.get('printed', current_printed) else 0
                b_count = updates.get('boxes_count', row['boxes_count'] if 'boxes_count' in row.keys() else data.get('boxes_count'))

                # Ð”Ð¾ÑÑ‚Ð°ÐµÐ¼ ÑÑƒÐ¼Ð¼Ñƒ
                t_val = updates.get('total_value', data.get('total_value', 0.0))

                # Ð”ÐµÑ€Ð¶Ð¸Ð¼ JSON ÑÐ¸Ð½Ñ…Ñ€Ð¾Ð½Ð½Ñ‹Ð¼ Ñ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ°Ð¼Ð¸.
                data['printed'] = bool(printed)
                data['boxes_count'] = b_count

                # Ð’ÐÐ–ÐÐž: ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ Ð·Ð°Ð¿Ñ€Ð¾Ñ SQL, Ð´Ð¾Ð±Ð°Ð²Ð»ÑÑ total_value
                # Ð•ÑÐ»Ð¸ Ñƒ Ð²Ð°Ñ ÑÑ‚Ð°Ñ€Ð°Ñ ÑÑ‚Ñ€ÑƒÐºÑ‚ÑƒÑ€Ð° Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ orders, Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾, Ð¿Ñ€Ð¸Ð´ÐµÑ‚ÑÑ Ð´ÐµÐ»Ð°Ñ‚ÑŒ ALTER TABLE Ð·Ð°Ñ€Ð°Ð½ÐµÐµ,
                # Ð¸Ð»Ð¸ Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ ÑÑƒÐ¼Ð¼Ñƒ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð²Ð½ÑƒÑ‚Ñ€Ð¸ JSON (order_data).
                # Ð¥Ñ€Ð°Ð½ÐµÐ½Ð¸Ðµ Ð’ÐÐ£Ð¢Ð Ð˜ JSON Ð¿Ñ€Ð¾Ñ‰Ðµ Ð¸ Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½ÐµÐµ, ÐµÑÐ»Ð¸ Ð½Ðµ Ñ…Ð¾Ñ‚Ð¸Ñ‚Ðµ Ð¼ÐµÐ½ÑÑ‚ÑŒ ÑÑ…ÐµÐ¼Ñƒ Ð‘Ð”:

                conn.execute("UPDATE orders SET order_data=?, delivery_date=?, production_date=?, printed=?, boxes_count=?, updated_at=? WHERE order_id=?",
                             (json.dumps(data), d_date, p_date, printed, b_count, datetime.now().isoformat(), oid))

                # Ð•ÑÐ»Ð¸ Ð²Ñ‹ Ð´Ð¾Ð±Ð°Ð²Ð¸Ð»Ð¸ ÐºÐ¾Ð»Ð¾Ð½ÐºÑƒ total_value Ñ„Ð¸Ð·Ð¸Ñ‡ÐµÑÐºÐ¸ Ð² Ð‘Ð” Ñ‡ÐµÑ€ÐµÐ· ALTER TABLE Ð²Ñ‹ÑˆÐµ:
                try:
                    conn.execute("UPDATE orders SET total_value=? WHERE order_id=?", (t_val, oid))
                except: pass # Ð˜Ð³Ð½Ð¾Ñ€Ð¸Ñ€ÑƒÐµÐ¼, ÐµÑÐ»Ð¸ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ Ð½ÐµÑ‚

                return True
        return False

    def mark_order_printed(self, order_id: str):
        """ÐžÑ‚Ð¼ÐµÑ‚Ð¸Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð· ÐºÐ°Ðº Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½Ð½Ñ‹Ð¹"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Ð¡Ð¸Ð½Ñ…Ñ€Ð¾Ð½Ð½Ð¾ Ð¾Ð±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ Ð¸ ÐºÐ¾Ð»Ð¾Ð½ÐºÑƒ, Ð¸ JSON order_data['printed'],
        # Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð¿Ð¾ÑÐ»ÐµÐ´ÑƒÑŽÑ‰Ð¸Ðµ update_order(...) Ð½Ðµ Ð¾Ñ‚ÐºÐ°Ñ‚Ñ‹Ð²Ð°Ð»Ð¸ ÑÑ‚Ð°Ñ‚ÑƒÑ.
        row = cursor.execute('SELECT order_data FROM orders WHERE order_id = ?', (order_id,)).fetchone()
        if row and row['order_data']:
            try:
                data = json.loads(row['order_data'])
            except Exception:
                data = {}
            data['printed'] = True
            if not data.get('status'):
                data['status'] = 'completed'
            cursor.execute('''
                UPDATE orders SET printed = 1, order_data = ?, updated_at = ? WHERE order_id = ?
            ''', (json.dumps(data), datetime.now().isoformat(), order_id))
        else:
            cursor.execute('''
                UPDATE orders SET printed = 1, updated_at = ? WHERE order_id = ?
            ''', (datetime.now().isoformat(), order_id))

        conn.commit()
        conn.close()

    def delete_order(self, order_id: str) -> bool:
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð·"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM orders WHERE order_id = ?', (order_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()
        return deleted

    def get_order(self, order_id: str) -> dict:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¾Ð´Ð¸Ð½ Ð·Ð°ÐºÐ°Ð· Ð¿Ð¾ ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        order_data = json.loads(row['order_data'])
        order_data['printed'] = bool(row['printed'])
        order_data['status'] = row['status']
        order_data['warehouse_id'] = row['warehouse_id']

        # Ð‘ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾Ðµ Ð¿Ð¾Ð»ÑƒÑ‡ÐµÐ½Ð¸Ðµ delivery_date Ð¸ production_date
        try:
            order_data['delivery_date'] = row['delivery_date']
        except (KeyError, IndexError):
            order_data['delivery_date'] = None

        try:
            order_data['production_date'] = row['production_date']
        except (KeyError, IndexError):
            order_data['production_date'] = None

        # Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ð¿Ñ€Ð¾Ð³Ñ€ÐµÑÑ ÐºÐ¾Ð¼Ð¿Ð»ÐµÐºÑ‚Ð°Ñ†Ð¸Ð¸
        picking_progress = self.get_picking_progress(order_id)
        if order_data.get('artikel') and picking_progress:
            for artikel in order_data['artikel']:
                artikel_nr = str(artikel.get('artikel_nr') or artikel.get('nummer') or '').strip()
                artikel_nr_norm = artikel_nr.zfill(5) if artikel_nr.isdigit() else artikel_nr
                for prog in picking_progress:
                    prog_nr = str(prog['artikel_nr'] or '').strip()
                    prog_nr_norm = prog_nr.zfill(5) if prog_nr.isdigit() else prog_nr
                    if artikel_nr_norm == prog_nr_norm:
                        artikel['picked'] = prog['picked_qty']
                        artikel['checked'] = prog['checked']
                        break

        # Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÑŽ Ð¾ Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ð¸
        assignment = self.get_order_assignment(order_id)
        if assignment:
            order_data['assignment'] = assignment

        conn.close()
        return order_data

    def get_all_orders(self) -> list:
        """Ð’Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ Ð’Ð¡Ð• Ð·Ð°ÐºÐ°Ð·Ñ‹, Ð¾Ñ‚ÑÐ¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ñ‹Ðµ Ð¿Ð¾ Ð´Ð°Ñ‚Ðµ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Ð‘ÐµÑ€ÐµÐ¼ Ð’Ð¡Ð• Ð·Ð°ÐºÐ°Ð·Ñ‹, ÑÐ¾Ñ€Ñ‚Ð¸Ñ€ÑƒÐµÐ¼ Ð¿Ð¾ Ð´Ð°Ñ‚Ðµ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ (ÑÐ½Ð°Ñ‡Ð°Ð»Ð° Ð½Ð¾Ð²Ñ‹Ðµ)
        cursor.execute('SELECT * FROM orders ORDER BY delivery_date DESC')
        return self._process_order_rows(cursor.fetchall())

    def get_orders_by_date(self, target_date: str) -> list:
        """Ð”Ð»Ñ Ð°Ñ€Ñ…Ð¸Ð²Ð°: Ð·Ð°ÐºÐ°Ð·Ñ‹ Ð·Ð° ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½ÑƒÑŽ Ð²Ñ‹Ð±Ñ€Ð°Ð½Ð½ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE delivery_date = ?', (target_date,))
        return self._process_order_rows(cursor.fetchall())

    def _process_order_rows(self, rows) -> list:
        """ÐžÐ±Ð¾Ð³Ð°Ñ‰Ð°ÐµÑ‚ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ð¾Ð² Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÐµÐ¹ Ð¾ Ð¿Ñ€Ð¾Ð³Ñ€ÐµÑÑÐµ Ð¸ ÑÐ±Ð¾Ñ€Ñ‰Ð¸ÐºÐ°Ð¼Ð¸"""
        orders = []
        if not rows:
            return []

        # ÐšÑÑˆ Ð°Ð´Ñ€ÐµÑÐ¾Ð² Ð¸Ð· client_routes (kunden_nr -> address string)
        _address_cache = None
        def _get_address(kunden_nr):
            nonlocal _address_cache
            if _address_cache is None:
                _address_cache = {}
                try:
                    conn2 = self.get_connection()
                    for cr in conn2.execute('SELECT client_id, address, plz, city FROM client_routes WHERE address IS NOT NULL AND address != ""'):
                        addr_parts = [cr['address'] or '', cr['plz'] or '', cr['city'] or '']
                        _address_cache[str(cr['client_id'])] = ', '.join(p for p in addr_parts if p)
                except Exception:
                    pass
            return _address_cache.get(str(kunden_nr), '')

        for row in rows:
            try:
                # Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ row['key'], Ñ‚Ð°Ðº ÐºÐ°Ðº ÑÑ‚Ð¾ sqlite3.Row
                order_id = row['order_id']
                raw_data = row['order_data']

                if not raw_data:
                    continue

                try:
                    order_data = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° JSON Ð² Ð·Ð°ÐºÐ°Ð·Ðµ {order_id}: {e}")
                    continue

                # Ð‘ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾ Ð¿Ð¾Ð´Ñ‚ÑÐ³Ð¸Ð²Ð°ÐµÐ¼ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¸Ð· ÐºÐ¾Ð»Ð¾Ð½Ð¾Ðº Ð‘Ð” Ð² Ð¾Ð±ÑŠÐµÐºÑ‚ Ð·Ð°ÐºÐ°Ð·Ð°
                # row.keys() Ð²Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ ÑÐ¿Ð¸ÑÐ¾Ðº Ð¸Ð¼ÐµÐ½ ÐºÐ¾Ð»Ð¾Ð½Ð¾Ðº
                columns = row.keys()

                order_data.update({
                    'order_id': order_id,
                    'printed': bool(row['printed']) if 'printed' in columns else False,
                    'status': row['status'] if 'status' in columns else 'pending',
                    'warehouse_id': str(row['warehouse_id']) if 'warehouse_id' in columns else '1',
                    'delivery_date': row['delivery_date'] if 'delivery_date' in columns else '',
                    'created_at': row['created_at'] if 'created_at' in columns else '',
                    'is_api_new': bool(row['is_api_new']) if 'is_api_new' in columns else False,
                })

                # ÐŸÐ¾Ð´Ñ‚ÑÐ³Ð¸Ð²Ð°ÐµÐ¼ Ð°Ð´Ñ€ÐµÑ Ð¸Ð· client_routes ÐµÑÐ»Ð¸ Ð² Ð·Ð°ÐºÐ°Ð·Ðµ Ð¿ÑƒÑÑ‚Ð¾Ð¹
                if not order_data.get('address'):
                    kn = order_data.get('kunden_nr', '')
                    if kn:
                        addr = _get_address(kn)
                        if addr:
                            order_data['address'] = addr

                # ÐŸÐ¾Ð´Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ð¿Ñ€Ð¾Ð³Ñ€ÐµÑÑ ÐºÐ¾Ð¼Ð¿Ð»ÐµÐºÑ‚Ð°Ñ†Ð¸Ð¸ (Ð³Ð°Ð»Ð¾Ñ‡ÐºÐ¸)
                try:
                    picking_progress = self.get_picking_progress(order_id)
                    if picking_progress and 'artikel' in order_data:
                        for art in order_data['artikel']:
                            # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» (Ð½Ð¾Ð¼ÐµÑ€ Ð¸Ð»Ð¸ id)
                            art_nr = str(art.get('artikel_nr') or art.get('nummer', '')).strip()
                            art_nr_norm = art_nr.zfill(5) if art_nr.isdigit() else art_nr
                            for prog in picking_progress:
                                prog_nr = str(prog['artikel_nr'] or '').strip()
                                prog_nr_norm = prog_nr.zfill(5) if prog_nr.isdigit() else prog_nr
                                if art_nr_norm == prog_nr_norm:
                                    art['picked'] = prog['picked_qty']
                                    art['checked'] = bool(prog['checked'])
                except Exception as pe:
                    logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ Ð¿Ñ€Ð¾Ð³Ñ€ÐµÑÑÐ° Ð´Ð»Ñ {order_id}: {pe}")

                # ÐŸÐ¾Ð´Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÑŽ Ð¾ ÑÐ±Ð¾Ñ€Ñ‰Ð¸ÐºÐµ
                try:
                    assignment = self.get_order_assignment(order_id)
                    if assignment:
                        order_data['assignment'] = assignment
                except:
                    pass

                # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð³Ð¾Ñ‚Ð¾Ð²Ñ‹Ð¹ Ð·Ð°ÐºÐ°Ð· Ð² ÑÐ¿Ð¸ÑÐ¾Ðº
                orders.append(order_data)

            except Exception as e:
                # Ð’Ð°Ð¶Ð½Ð¾: Ð·Ð´ÐµÑÑŒ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ logger, ÐºÐ¾Ñ‚Ð¾Ñ€Ñ‹Ð¹ Ð¾Ð¿Ñ€ÐµÐ´ÐµÐ»ÐµÐ½ Ð² Ð½Ð°Ñ‡Ð°Ð»Ðµ Ñ„Ð°Ð¹Ð»Ð°
                logger.error(f"ÐšÑ€Ð¸Ñ‚Ð¸Ñ‡ÐµÑÐºÐ°Ñ Ð¾ÑˆÐ¸Ð±ÐºÐ° Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸ ÑÑ‚Ñ€Ð¾ÐºÐ¸ Ð·Ð°ÐºÐ°Ð·Ð°: {e}", exc_info=True)
                continue

        # Ð’Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÐ¼ Ð½Ð°ÐºÐ¾Ð¿Ð»ÐµÐ½Ð½Ñ‹Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
        return orders

    def get_orders_for_warehouse(self, warehouse_id: str) -> list:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ð´Ð»Ñ ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ð¾Ð³Ð¾ ÑÐºÐ»Ð°Ð´Ð°"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM orders WHERE warehouse_id = ? AND printed = 0 ORDER BY created_at ASC
        ''', (warehouse_id,))

        rows = cursor.fetchall()

        orders = []
        for row in rows:
            order_data = json.loads(row['order_data'])
            order_data['printed'] = bool(row['printed'])
            order_data['status'] = row['status']
            order_data['warehouse_id'] = row['warehouse_id']

            orders.append({
                'order_id': row['order_id'],
                'data': order_data
            })

        conn.close()
        return orders

    # ============================================
    # Ð£Ð¡Ð›ÐžÐ’ÐÐ«Ð• ÐÐ Ð¢Ð˜ÐšÐ£Ð›Ð«
    # ============================================
    def get_conditional_articles(self) -> list:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð²ÑÐµ ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñ‹"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM conditional_articles ORDER BY article_number')
        rows = cursor.fetchall()

        articles = []
        for row in rows:
            articles.append({
                'article_id': row['article_id'],
                'article_number': row['article_number'],
                'description': row['description'],
                'created_at': row['created_at']
            })

        conn.close()
        return articles

    def add_conditional_article(self, article_number: str, description: str = '') -> bool:
        """Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO conditional_articles (article_number, description, created_at)
                VALUES (?, ?, ?)
            ''', (article_number, description, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    def remove_conditional_article(self, article_id: int) -> bool:
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM conditional_articles WHERE article_id = ?', (article_id,))
        deleted = cursor.rowcount > 0

        conn.commit()
        conn.close()
        return deleted

    def is_conditional_article(self, article_number: str) -> bool:
        """ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ ÑÐ²Ð»ÑÐµÑ‚ÑÑ Ð»Ð¸ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ð¼"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM conditional_articles WHERE article_number = ?', (article_number,))
        count = cursor.fetchone()[0]

        conn.close()
        return count > 0

    # ============================================
    # ÐšÐžÐœÐŸÐ›Ð•ÐšÐ¢ÐÐ¦Ð˜Ð¯ Ð—ÐÐšÐÐ—ÐžÐ’
    # ============================================
    def init_order_picking(self, order_id: str, artikel_list: list):
        """Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ Ð¿Ñ€Ð¾Ð³Ñ€ÐµÑÑ ÐºÐ¾Ð¼Ð¿Ð»ÐµÐºÑ‚Ð°Ñ†Ð¸Ð¸ Ð´Ð»Ñ Ð½Ð¾Ð²Ð¾Ð³Ð¾ Ð·Ð°ÐºÐ°Ð·Ð°"""
        conn = self.get_connection()
        cursor = conn.cursor()

        for artikel in artikel_list:
            try:
                cursor.execute('''
                    INSERT INTO order_picking (order_id, artikel_nr, pos, total_qty, picked_qty, checked, updated_at)
                    VALUES (?, ?, ?, ?, 0, 0, ?)
                ''', (order_id, artikel.get('artikel_nr'), artikel.get('pos', 0),
                      artikel.get('menge', 0), datetime.now().isoformat()))
            except sqlite3.IntegrityError:
                # Ð£Ð¶Ðµ ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÐµÑ‚, Ð¿Ñ€Ð¾Ð¿ÑƒÑÐºÐ°ÐµÐ¼
                pass

        conn.commit()
        conn.close()

    def update_picking_progress(self, order_id: str, artikel_nr: str, picked_qty: int, checked: bool):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð¿Ñ€Ð¾Ð³Ñ€ÐµÑÑ ÐºÐ¾Ð¼Ð¿Ð»ÐµÐºÑ‚Ð°Ñ†Ð¸Ð¸ Ð¿Ð¾Ð·Ð¸Ñ†Ð¸Ð¸"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE order_picking
            SET picked_qty = ?, checked = ?, updated_at = ?
            WHERE order_id = ? AND artikel_nr = ?
        ''', (picked_qty, 1 if checked else 0, datetime.now().isoformat(), order_id, artikel_nr))

        conn.commit()
        conn.close()

    def get_picking_progress(self, order_id: str) -> list:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¿Ñ€Ð¾Ð³Ñ€ÐµÑÑ ÐºÐ¾Ð¼Ð¿Ð»ÐµÐºÑ‚Ð°Ñ†Ð¸Ð¸ Ð·Ð°ÐºÐ°Ð·Ð°"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT artikel_nr, pos, total_qty, picked_qty, checked, updated_at
            FROM order_picking
            WHERE order_id = ?
            ORDER BY pos
        ''', (order_id,))

        rows = cursor.fetchall()
        progress = []
        for row in rows:
            progress.append({
                'artikel_nr': row['artikel_nr'],
                'pos': row['pos'],
                'total_qty': row['total_qty'],
                'picked_qty': row['picked_qty'],
                'checked': bool(row['checked']),
                'updated_at': row['updated_at']
            })

        conn.close()
        return progress

    def assign_user_to_order(self, order_id: str, user_id: int, username: str, force=False):
        """
        ÐÐ°Ð·Ð½Ð°Ñ‡Ð¸Ñ‚ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ Ð½Ð° Ð·Ð°ÐºÐ°Ð·

        Args:
            order_id: ID Ð·Ð°ÐºÐ°Ð·Ð°
            user_id: ID Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ
            username: Ð˜Ð¼Ñ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ
            force: ÐŸÑ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð¾ Ð¿ÐµÑ€ÐµÐ½Ð°Ð·Ð½Ð°Ñ‡Ð¸Ñ‚ÑŒ (Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð´Ð»Ñ Ð°Ð´Ð¼Ð¸Ð½Ð°)

        Returns:
            dict: {'success': bool, 'message': str, 'assigned_to': str}
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼, Ð½Ðµ Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½ Ð»Ð¸ ÑƒÐ¶Ðµ Ð·Ð°ÐºÐ°Ð·
        cursor.execute('''
            SELECT oa.user_id, oa.username,
                   COALESCE(NULLIF(u.display_name, ''), u.username, oa.username) AS display_name
            FROM order_assignments oa
            LEFT JOIN users u ON u.user_id = oa.user_id
            WHERE oa.order_id = ?
        ''', (order_id,))

        existing = cursor.fetchone()
        existing_display = (
            existing['display_name']
            if existing and 'display_name' in existing.keys() and existing['display_name']
            else (existing['username'] if existing else '')
        )

        if existing and not force:
            # Ð—Ð°ÐºÐ°Ð· ÑƒÐ¶Ðµ Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½ Ð´Ñ€ÑƒÐ³Ð¾Ð¼Ñƒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŽ
            conn.close()
            return {
                'success': False,
                'message': f"Ð—Ð°ÐºÐ°Ð· ÑƒÐ¶Ðµ Ð²Ð·ÑÑ‚ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¼ {existing['username']}",
                'assigned_to': existing_display
            }

        try:
            display_name = username
            cursor.execute(
                "SELECT COALESCE(NULLIF(display_name, ''), username) AS display_name FROM users WHERE user_id = ?",
                (user_id,)
            )
            urow = cursor.fetchone()
            if urow and urow['display_name']:
                display_name = urow['display_name']

            if existing and force:
                # ÐŸÑ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð¾Ðµ Ð¿ÐµÑ€ÐµÐ½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ (Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð°Ð´Ð¼Ð¸Ð½)
                cursor.execute('''
                    UPDATE order_assignments
                    SET user_id = ?, username = ?, assigned_at = ?
                    WHERE order_id = ?
                ''', (user_id, username, datetime.now().isoformat(), order_id))
                logger.info(f"Ð—Ð°ÐºÐ°Ð· {order_id} Ð¿ÐµÑ€ÐµÐ½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½ Ñ {existing['username']} Ð½Ð° {username} (force=True)")
            else:
                # ÐŸÐµÑ€Ð²Ð¾Ðµ Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ
                cursor.execute('''
                    INSERT INTO order_assignments (order_id, user_id, username, assigned_at, status)
                    VALUES (?, ?, ?, ?, 'picking')
                ''', (order_id, user_id, username, datetime.now().isoformat()))
                logger.info(f"Ð—Ð°ÐºÐ°Ð· {order_id} Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½ Ð½Ð° {username}")

            conn.commit()
            conn.close()
            return {
                'success': True,
                'message': f"Ð—Ð°ÐºÐ°Ð· Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½ Ð½Ð° {username}",
                'assigned_to': display_name
            }
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ñ Ð·Ð°ÐºÐ°Ð·Ð°: {e}")
            conn.close()
            return {
                'success': False,
                'message': f"ÐžÑˆÐ¸Ð±ÐºÐ°: {e}",
                'assigned_to': None
            }

    def get_picking_statistics(self, start_date: str = None, end_date: str = None) -> list:
        """Ð¡Ð¾Ð±Ð¸Ñ€Ð°ÐµÑ‚ KPI ÑÐ±Ð¾Ñ€Ñ‰Ð¸ÐºÐ¾Ð²: ÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ð·Ð°ÐºÐ°Ð·Ð¾Ð² Ð²Ð·ÑÐ»Ð¸ Ð¸ ÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ð¿Ð¾Ð·Ð¸Ñ†Ð¸Ð¹ Ñ€ÐµÐ°Ð»ÑŒÐ½Ð¾ Ð·Ð°ÐºÑ€Ñ‹Ð»Ð¸"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Ð¤Ð¾Ñ€Ð¼Ð¸Ñ€ÑƒÐµÐ¼ Ñ€Ð°ÑÑˆÐ¸Ñ€ÐµÐ½Ð½Ñ‹Ð¹ Ð·Ð°Ð¿Ñ€Ð¾Ñ
        # ÐœÑ‹ Ð±ÐµÑ€ÐµÐ¼ Ð²ÑÐµÑ…, ÐºÑ‚Ð¾ Ð½Ð°Ð·Ð½Ð°Ñ‡Ð°Ð»ÑÑ Ð½Ð° Ð·Ð°ÐºÐ°Ð·Ñ‹, Ð¸ ÑÑ‡Ð¸Ñ‚Ð°ÐµÐ¼ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ Ð¾Ñ‚Ð¼ÐµÑ‡ÐµÐ½Ð½Ñ‹Ñ… (checked=1) Ð¿Ð¾Ð·Ð¸Ñ†Ð¸Ð¹
        query = '''
            SELECT
                oa.username,
                COUNT(DISTINCT oa.order_id) as orders_count,
                (
                    SELECT COUNT(*)
                    FROM order_picking op
                    WHERE op.order_id IN (SELECT order_id FROM order_assignments WHERE username = oa.username)
                    AND op.checked = 1
                ) as total_items
            FROM order_assignments oa
            WHERE 1=1
        '''
        params = []

        # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ñ„Ð¸Ð»ÑŒÑ‚Ñ€ Ð¿Ð¾ Ð´Ð°Ñ‚Ð°Ð¼, ÐµÑÐ»Ð¸ Ð¾Ð½Ð¸ Ð¿ÐµÑ€ÐµÐ´Ð°Ð½Ñ‹
        if start_date:
            query += " AND oa.assigned_at >= ?"
            params.append(f"{start_date} 00:00:00")
        if end_date:
            query += " AND oa.assigned_at <= ?"
            params.append(f"{end_date} 23:59:59")

        query += " GROUP BY oa.username ORDER BY total_items DESC"

        try:
            cursor.execute(query, params)
            rows = cursor.fetchall()

            stats = []
            for row in rows:
                stats.append({
                    'username': row['username'],
                    'orders_count': row['orders_count'] or 0,
                    'total_items': row['total_items'] or 0
                })

            return stats
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ð¾Ð»ÑƒÑ‡ÐµÐ½Ð¸Ñ ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ¸ KPI: {e}")
            return []
        finally:
            conn.close()

    def count_orders_by_production_date(self, production_date: str) -> int:
        """
        ÐŸÐ¾Ð´ÑÑ‡Ð¸Ñ‚Ð°Ñ‚ÑŒ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ Ð·Ð°ÐºÐ°Ð·Ð¾Ð², Ð·Ð°Ð¿Ð»Ð°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ñ‹Ñ… Ð½Ð° ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð°

        Args:
            production_date: Ð”Ð°Ñ‚Ð° Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð° Ð² Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ðµ 'YYYY-MM-DD'

        Returns:
            ÐšÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ Ð·Ð°ÐºÐ°Ð·Ð¾Ð² Ð½Ð° ÑÑ‚Ñƒ Ð´Ð°Ñ‚Ñƒ
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT COUNT(*) as cnt
                FROM orders
                WHERE production_date = ?
            ''', (production_date,))

            row = cursor.fetchone()
            return row['cnt'] if row else 0
        except Exception as e:
            logger.error(f"Error counting orders by production date: {e}")
            return 0
        finally:
            conn.close()

    def get_orders_by_production_date(self, production_date: str) -> list:
        """
        ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ð½Ð° ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð°

        Args:
            production_date: Ð”Ð°Ñ‚Ð° Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð° Ð² Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ðµ 'YYYY-MM-DD'

        Returns:
            Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT order_id, order_data, production_date
                FROM orders
                WHERE production_date = ?
            ''', (production_date,))

            rows = cursor.fetchall()
            orders = []
            for row in rows:
                orders.append({
                    'order_id': row['order_id'],
                    'order_data': row['order_data'],
                    'production_date': row['production_date']
                })
            return orders
        except Exception as e:
            logger.error(f"Error getting orders by production date: {e}")
            return []
        finally:
            conn.close()

    def get_plan_settings(self, user_id=None) -> dict:
        """
        ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¿Ð»Ð°Ð½Ð° Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð°

        Args:
            user_id: ID Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ (None Ð´Ð»Ñ Ð³Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ñ… Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº)

        Returns:
            Ð¡Ð»Ð¾Ð²Ð°Ñ€ÑŒ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº {'workdays': '...', 'visible_columns': '...'}
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            if user_id is None:
                cursor.execute('''
                    SELECT setting_key, setting_value
                    FROM plan_settings
                    WHERE user_id IS NULL
                ''')
            else:
                cursor.execute('''
                    SELECT setting_key, setting_value
                    FROM plan_settings
                    WHERE user_id = ?
                ''', (user_id,))

            rows = cursor.fetchall()
            settings = {}
            for row in rows:
                settings[row['setting_key']] = row['setting_value']

            return settings
        except Exception as e:
            logger.error(f"Error getting plan settings: {e}")
            return {}
        finally:
            conn.close()

    def get_order_assignment(self, order_id: str) -> dict:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ Ð½Ð° Ð·Ð°ÐºÐ°Ð·"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT oa.user_id, oa.username,
                   COALESCE(NULLIF(u.display_name, ''), u.username, oa.username) AS display_name,
                   oa.assigned_at, oa.status
            FROM order_assignments oa
            LEFT JOIN users u ON u.user_id = oa.user_id
            WHERE oa.order_id = ?
        ''', (order_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'user_id': row['user_id'],
                'username': row['username'],
                'display_name': row['display_name'] if 'display_name' in row.keys() else row['username'],
                'assigned_at': row['assigned_at'],
                'status': row['status']
            }
        return None

    def release_order_assignment(self, order_id: str):
        """ÐžÑÐ²Ð¾Ð±Ð¾Ð´Ð¸Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð· Ð¾Ñ‚ Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ñ"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM order_assignments WHERE order_id = ?', (order_id,))
        conn.commit()
        conn.close()

    # ============================================
    # Ð›ÐžÐ“Ð˜Ð¡Ð¢Ð˜ÐšÐ
    # ============================================
    def import_logistics_from_csv(self, csv_path: Path):
        """
        Ð˜Ð¼Ð¿Ð¾Ñ€Ñ‚ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² Ð¸Ð· KUNDENLISTE CSV Ð¸ Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð¾Ð²

        Ð›Ð¾Ð³Ð¸ÐºÐ° Ð¾Ð¿Ñ€ÐµÐ´ÐµÐ»ÐµÐ½Ð¸Ñ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°:
        1. Kategorie = 2 (ÑÐºÐ»Ð°Ð´) + Region Ð¾Ð¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÑ‚ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ (Ost, SÃ¼d, West, Nord, Mitte)
        2. Kategorie = 1 (Ð¿Ñ€ÑÐ¼Ð°Ñ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ°) â†’ free (ÑÐ²Ð¾Ð±Ð¾Ð´Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ñ‹, Ñ€ÑƒÑ‡Ð½Ð¾Ð¹ Ñ€ÐµÐ¶Ð¸Ð¼)
        3. Mix Markt Ð¼Ð°Ð³Ð°Ð·Ð¸Ð½Ñ‹ (Ð¿Ð»Ð°Ñ‚ÐµÐ»ÑŒÑ‰Ð¸Ðº Monolith) + Kategorie = 2 â†’ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ Ð¿Ð¾ Region

        Ð’Ñ‹Ð·Ñ‹Ð²Ð°ÐµÑ‚ÑÑ Ð¿Ñ€Ð¸ ÑÑ‚Ð°Ñ€Ñ‚Ðµ ÑÐµÑ€Ð²ÐµÑ€Ð° Ð´Ð»Ñ Ð¿ÐµÑ€Ð²Ð¾Ð½Ð°Ñ‡Ð°Ð»ÑŒÐ½Ð¾Ð³Ð¾ Ð·Ð°Ð¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹
        """
        import csv

        # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼, Ð¿ÑƒÑÑ‚Ð° Ð»Ð¸ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð°
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM client_routes')

        if cursor.fetchone()[0] > 0:
            conn.close()
            logger.info("Client routes table already populated, skipping CSV import")
            return

        if not csv_path.exists():
            conn.close()
            logger.warning(f"Customer list CSV not found at {csv_path}, skipping logistics import")
            return

        logger.info(f"Importing client routes from {csv_path}...")

        # ÐœÐ°Ð¿Ð¿Ð¸Ð½Ð³ Ñ€ÐµÐ³Ð¸Ð¾Ð½Ð° Ð½Ð° route_id (Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð´Ð»Ñ ÑÐºÐ»Ð°Ð´Ð¾Ð² - Kategorie = 2)
        # Ð’Ð°Ð¶Ð½Ð¾: Ñ€ÐµÐ³Ð¸Ð¾Ð½Ñ‹ Ð¼Ð¾Ð³ÑƒÑ‚ ÑÐ¾Ð´ÐµÑ€Ð¶Ð°Ñ‚ÑŒ Ð¿Ñ€Ð¾Ð±ÐµÐ»Ñ‹ Ð¸ Ñ€Ð°Ð·Ð½Ñ‹Ðµ Ð²Ð°Ñ€Ð¸Ð°Ð½Ñ‚Ñ‹ Ð½Ð°Ð¿Ð¸ÑÐ°Ð½Ð¸Ñ
        region_to_route = {
            'ost': 'ost',
            'fg ost': 'ost',
            'sÃ¼d': 'sued',
            'sÃ£Â¼d': 'sued',  # ÐšÐ¾Ð´Ð¸Ñ€Ð¾Ð²ÐºÐ° cp1252 Ð´Ð»Ñ Ã¼
            'sÃ¼d!!!': 'sued',  # Ð’Ð°Ñ€Ð¸Ð°Ð½Ñ‚ Ñ Ð²Ð¾ÑÐºÐ»Ð¸Ñ†Ð°Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ð¼Ð¸ Ð·Ð½Ð°ÐºÐ°Ð¼Ð¸
            'fg sÃ¼d': 'sued',
            'fg sÃ£Â¼d': 'sued',
            'west': 'west',
            'fg west': 'west',
            'west (s. info)': 'west',  # Ð’Ð°Ñ€Ð¸Ð°Ð½Ñ‚ Ñ Ð¿Ñ€Ð¸Ð¼ÐµÑ‡Ð°Ð½Ð¸ÐµÐ¼
            'nord': 'nord',
            'fg nord': 'nord',
            'nord lager': 'nord',  # Ð’Ð°Ñ€Ð¸Ð°Ð½Ñ‚ "ÑÐºÐ»Ð°Ð´ Nord"
            'mitte': 'mitte',
            'fg mitte': 'mitte',
        }

        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ ÑƒÐ´Ð°Ð»ÑÐµÑ‚ BOM
                reader = csv.DictReader(f, delimiter=';')
                imported_count = 0
                skipped_count = 0
                duplicate_count = 0
                seen_ids = set()  # Ð”Ð»Ñ Ð¾Ñ‚ÑÐ»ÐµÐ¶Ð¸Ð²Ð°Ð½Ð¸Ñ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ð¾Ð²

                for row in reader:
                    # Ð§Ð¸Ñ‚Ð°ÐµÐ¼ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¸Ð· CSV (ÑƒÑ‡Ð¸Ñ‚Ñ‹Ð²Ð°ÐµÐ¼ Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ñ‹Ð¹ BOM Ð² Ð·Ð°Ð³Ð¾Ð»Ð¾Ð²ÐºÐ°Ñ…)
                    client_id = row.get('KD.-ID', row.get('\ufeffKD.-ID', '')).strip()  # ÐÐ¾Ð¼ÐµÑ€ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°
                    firma = row.get('Firma', '').strip()  # ÐÐ°Ð·Ð²Ð°Ð½Ð¸Ðµ ÐºÐ¾Ð¼Ð¿Ð°Ð½Ð¸Ð¸
                    region_raw = row.get('Region', '').strip()  # Ð ÐµÐ³Ð¸Ð¾Ð½
                    kategorie = row.get('Kategorie', '').strip()  # 1=Ð¼Ð°Ð³Ð°Ð·Ð¸Ð½, 2=ÑÐºÐ»Ð°Ð´

                    if not client_id or not firma:
                        skipped_count += 1
                        continue

                    # ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° Ð½Ð° Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹
                    if client_id in seen_ids:
                        duplicate_count += 1
                        logger.debug(f"Duplicate client_id skipped: {client_id} ({firma})")
                        continue
                    seen_ids.add(client_id)

                    # ÐÐ¾Ñ€Ð¼Ð°Ð»Ð¸Ð·ÑƒÐµÐ¼ Ñ€ÐµÐ³Ð¸Ð¾Ð½: ÑƒÐ±Ð¸Ñ€Ð°ÐµÐ¼ Ð¿Ñ€Ð¾Ð±ÐµÐ»Ñ‹, Ð¿ÐµÑ€ÐµÐ²Ð¾Ð´Ð¸Ð¼ Ð² lower case
                    region = region_raw.lower().strip()

                    # ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ Ð½Ð° Ð¾ÑÐ½Ð¾Ð²Ðµ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¸ Ð¸ Ñ€ÐµÐ³Ð¸Ð¾Ð½Ð°
                    route_id = 'free'  # ÐŸÐ¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ

                    if kategorie == '2':
                        # ÐšÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ 2 = ÑÐºÐ»Ð°Ð´ â†’ Ð¾Ð¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ Ð¿Ð¾ Ñ€ÐµÐ³Ð¸Ð¾Ð½Ñƒ
                        route_id = region_to_route.get(region, 'free')

                        if route_id == 'free' and region:
                            # Ð ÐµÐ³Ð¸Ð¾Ð½ Ð½Ðµ Ñ€Ð°ÑÐ¿Ð¾Ð·Ð½Ð°Ð½ - Ð»Ð¾Ð³Ð¸Ñ€ÑƒÐµÐ¼ Ð´Ð»Ñ Ð°Ð½Ð°Ð»Ð¸Ð·Ð°
                            logger.warning(f"Client {client_id} ({firma}): Unknown region '{region}' for Kategorie=2, using route=free")
                        else:
                            logger.debug(f"Client {client_id} ({firma}): Kategorie=2 (ÑÐºÐ»Ð°Ð´), Region={region} â†’ route={route_id}")
                    elif kategorie == '1':
                        # ÐšÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ 1 = Ð¿Ñ€ÑÐ¼Ð°Ñ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ° â†’ ÑÐ²Ð¾Ð±Ð¾Ð´Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ñ‹ (Ñ€ÑƒÑ‡Ð½Ð¾Ð¹ Ñ€ÐµÐ¶Ð¸Ð¼)
                        route_id = 'free'
                        logger.debug(f"Client {client_id} ({firma}): Kategorie=1 (Ð¼Ð°Ð³Ð°Ð·Ð¸Ð½) â†’ route=free (Ñ€ÑƒÑ‡Ð½Ð¾Ð¹ Ñ€ÐµÐ¶Ð¸Ð¼)")
                    else:
                        # ÐÐµÐ¸Ð·Ð²ÐµÑÑ‚Ð½Ð°Ñ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ â†’ free
                        logger.warning(f"Client {client_id} ({firma}): Unknown Kategorie={kategorie}, using route=free")

                    # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð² Ð±Ð°Ð·Ñƒ
                    cursor.execute('''
                        INSERT INTO client_routes (client_id, client_name, route_id, updated_at)
                        VALUES (?, ?, ?, ?)
                    ''', (
                        client_id,
                        firma,
                        route_id,
                        datetime.now().isoformat()
                    ))
                    imported_count += 1

                conn.commit()
                logger.info(f"Successfully imported {imported_count} client routes from CSV (skipped {skipped_count} invalid entries, {duplicate_count} duplicates)")

        except Exception as e:
            logger.error(f"Error importing client routes from CSV: {e}")
            conn.rollback()

        conn.close()

    def get_all_logistics(self) -> dict:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ñ‹ Ð¸ Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ñ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² (Ð¡ ÐÐ”Ð Ð•Ð¡ÐÐœÐ˜)"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # ÐœÐ°Ñ€ÑˆÑ€ÑƒÑ‚Ñ‹
        cursor.execute('SELECT * FROM logistics_routes ORDER BY route_id')
        route_rows = cursor.fetchall()
        routes = [dict(row) for row in route_rows]
        # Ð”ÐµÐºÐ¾Ð´Ð¸Ñ€ÑƒÐµÐ¼ JSON Ð´Ð½ÐµÐ¹
        for r in routes:
            try: r['delivery_days'] = json.loads(r['delivery_days'])
            except: r['delivery_days'] = []

        # ÐšÐ»Ð¸ÐµÐ½Ñ‚Ñ‹ (Ð¡ ÐÐžÐ’Ð«ÐœÐ˜ ÐŸÐžÐ›Ð¯ÐœÐ˜ + is_new)
        # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ Ð½Ð°Ð»Ð¸Ñ‡Ð¸Ðµ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ is_new
        cursor.execute("PRAGMA table_info(client_routes)")
        columns = [col[1] for col in cursor.fetchall()]
        has_is_new = 'is_new' in columns

        has_monolith_id = 'monolith_client_id' in columns

        extended_client_cols = [
            'first_name', 'last_name', 'company_name', 'website_url', 'vat_id',
            'phone', 'position_title', 'country', 'price_list', 'discount_enabled',
            'discount_percent', 'payment_terms', 'tags'
        ]
        has_extended_client_cols = all(col in columns for col in extended_client_cols)

        if has_is_new:
            cursor.execute(f'''
                SELECT
                    cr.client_id,
                    cr.client_name,
                    cr.email,
                    cr.address,
                    cr.plz,
                    cr.city,
                    cr.route_id,
                    cr.transport_type,
                    cr.delivery_point,
                    cr.route_rules,
                    cr.is_new,
                    {'cr.monolith_client_id,' if has_monolith_id else ''}
                    COALESCE(lr.route_id, cr.route_id) AS resolved_route_id,
                    COALESCE(lr.route_name, cr.route_id, 'free') AS resolved_route_name
                FROM client_routes cr
                LEFT JOIN logistics_routes lr
                    ON lower(trim(cr.route_id)) = lower(trim(lr.route_id))
                    OR lower(trim(cr.route_id)) = lower(trim(lr.route_name))
                ORDER BY cr.is_new DESC, cr.client_name
            ''')
        else:
            cursor.execute(f'''
                SELECT
                    cr.client_id,
                    cr.client_name,
                    cr.email,
                    cr.address,
                    cr.plz,
                    cr.city,
                    cr.route_id,
                    cr.transport_type,
                    cr.delivery_point,
                    cr.route_rules,
                    {'cr.monolith_client_id,' if has_monolith_id else ''}
                    COALESCE(lr.route_id, cr.route_id) AS resolved_route_id,
                    COALESCE(lr.route_name, cr.route_id, 'free') AS resolved_route_name
                FROM client_routes cr
                LEFT JOIN logistics_routes lr
                    ON lower(trim(cr.route_id)) = lower(trim(lr.route_id))
                    OR lower(trim(cr.route_id)) = lower(trim(lr.route_name))
                ORDER BY cr.client_name
            ''')
        client_rows = cursor.fetchall()

        ext_map = {}
        if has_extended_client_cols:
            cursor.execute('''
                SELECT
                    client_id, first_name, last_name, company_name, website_url, vat_id,
                    phone, position_title, country, price_list, discount_enabled,
                    discount_percent, payment_terms, tags
                FROM client_routes
            ''')
            for erow in cursor.fetchall():
                ext_map[str(erow['client_id'])] = dict(erow)

        clients = []
        for row in client_rows:
            ext = ext_map.get(str(row['client_id']), {})
            clients.append({
                'client_id': row['client_id'],
                'client_name': row['client_name'],
                'email': row['email'] or '',
                'first_name': ext.get('first_name', ''),
                'last_name': ext.get('last_name', ''),
                'company_name': ext.get('company_name', ''),
                'website_url': ext.get('website_url', ''),
                'vat_id': ext.get('vat_id', ''),
                'phone': ext.get('phone', ''),
                'position_title': ext.get('position_title', ''),
                'address': row['address'] or '',
                'plz': row['plz'] or '',
                'city': row['city'] or '',
                'route_id': row['resolved_route_id'] or row['route_id'] or 'free',
                'route_name': row['resolved_route_name'] or row['route_id'] or 'free',
                'country': ext.get('country', ''),
                'price_list': ext.get('price_list', ''),
                'discount_enabled': int(ext.get('discount_enabled') or 0),
                'discount_percent': float(ext.get('discount_percent') or 0),
                'payment_terms': ext.get('payment_terms', ''),
                'tags': ext.get('tags', ''),
                'transport_type': row['transport_type'] or 'Eigenes Auto',
                'delivery_point': row['delivery_point'] or 'Gesch?ft',
                'route_rules': row['route_rules'] or '[]',
                'is_new': row['is_new'] if has_is_new else 0,
                'monolith_client_id': row['monolith_client_id'] if has_monolith_id else ''
            })

        conn.close()
        return {'routes': routes, 'clients': clients}

    def save_client_route(self, client_id: str, client_name: str, route_id: str) -> bool:
        """ÐÐ°Ð·Ð½Ð°Ñ‡Ð¸Ñ‚ÑŒ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ñƒ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼, ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÐµÑ‚ Ð»Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚
            cursor.execute('SELECT client_id FROM client_routes WHERE client_id = ?', (client_id,))
            exists = cursor.fetchone()

            if exists:
                # UPDATE
                cursor.execute('''
                    UPDATE client_routes
                    SET client_name = ?, route_id = ?, updated_at = ?
                    WHERE client_id = ?
                ''', (client_name, route_id, datetime.now().isoformat(), client_id))
            else:
                # INSERT
                cursor.execute('''
                    INSERT INTO client_routes (client_id, client_name, route_id, updated_at)
                    VALUES (?, ?, ?, ?)
                ''', (client_id, client_name, route_id, datetime.now().isoformat()))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Error saving client route: {e}")
            conn.close()
            return False

    def update_logistics_route(self, route_id: str, delivery_days: list, lead_time: int) -> bool:
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð¿Ð°Ñ€Ð°Ð¼ÐµÑ‚Ñ€Ñ‹ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                UPDATE logistics_routes
                SET delivery_days = ?, lead_time = ?, updated_at = ?
                WHERE route_id = ?
            ''', (json.dumps(delivery_days), lead_time, datetime.now().isoformat(), route_id))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Error updating logistics route: {e}")
            conn.close()
            return False

    def update_orders_route_by_client(self, client_id: str, route_id: str) -> list:
        """
        ???????? route_id ? route_name ?? ???? ???????? ??????? ???????.
        ???????????? ????????????? ??? ?? client_id, ??? ? ?? monolith_client_id.

        Returns:
            ?????? order_id ??????????? ???????.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        updated_order_ids = []

        try:
            # 1. ???????? route_name ?? route_id
            cursor.execute("SELECT route_name FROM logistics_routes WHERE route_id = ?", (route_id,))
            row = cursor.fetchone()
            route_name = row['route_name'] if row else route_id

            # 2. ???????? ??? ?????????????? ???????: client_id + monolith_client_id
            cursor.execute(
                "SELECT client_id, monolith_client_id FROM client_routes WHERE client_id = ?",
                (client_id,)
            )
            c_row = cursor.fetchone()
            compare_ids = set()
            for raw_id in (client_id, (c_row['client_id'] if c_row else None), (c_row['monolith_client_id'] if c_row else None)):
                rid = str(raw_id or '').strip()
                if not rid:
                    continue
                compare_ids.add(rid.lstrip('0') or rid)

            # 3. ???? ??? ???????? ?????? ? kunden_nr, ??????????? ? ????? ??????????????? ???????
            cursor.execute("SELECT order_id, order_data FROM orders WHERE status != 'archived'")
            orders = cursor.fetchall()

            for order in orders:
                try:
                    order_data = json.loads(order['order_data'])
                    order_kunden = str(order_data.get('kunden_nr', '')).strip()
                    order_kunden_normalized = order_kunden.lstrip('0') if order_kunden else ''

                    if order_kunden and order_kunden_normalized in compare_ids:
                        old_route = order_data.get('route_id')
                        old_name = order_data.get('route_name')
                        if old_route != route_id or old_name != route_name:
                            order_data['route_id'] = route_id
                            order_data['route_name'] = route_name

                            cursor.execute(
                                """
                                UPDATE orders SET order_data = ?, updated_at = ?
                                WHERE order_id = ?
                                """,
                                (json.dumps(order_data, ensure_ascii=False), datetime.now().isoformat(), order['order_id'])
                            )

                            updated_order_ids.append(order['order_id'])
                            logger.info(f"Updated route for order {order['order_id']}: {old_route}/{old_name} -> {route_id}/{route_name}")

                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Error parsing order {order['order_id']}: {e}")
                    continue

            conn.commit()
            logger.info(f"Updated {len(updated_order_ids)} orders for client {client_id} with route {route_id}")

        except Exception as e:
            logger.error(f"Error updating orders route for client {client_id}: {e}")
        finally:
            conn.close()

        return updated_order_ids

    def update_orders_route_name_by_route_id(self, route_id: str, new_route_name: str) -> list:
        """
        ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ route_name Ð²Ð¾ Ð²ÑÐµÑ… Ð·Ð°ÐºÐ°Ð·Ð°Ñ… Ñ Ð´Ð°Ð½Ð½Ñ‹Ð¼ route_id.
        Ð’Ñ‹Ð·Ñ‹Ð²Ð°ÐµÑ‚ÑÑ Ð¿Ñ€Ð¸ Ð¿ÐµÑ€ÐµÐ¸Ð¼ÐµÐ½Ð¾Ð²Ð°Ð½Ð¸Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°.

        Args:
            route_id: ID Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°
            new_route_name: ÐÐ¾Ð²Ð¾Ðµ Ð½Ð°Ð·Ð²Ð°Ð½Ð¸Ðµ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°

        Returns:
            Ð¡Ð¿Ð¸ÑÐ¾Ðº order_id Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ñ‹Ñ… Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        updated_order_ids = []

        try:
            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð²ÑÐµ Ð°ÐºÑ‚Ð¸Ð²Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ñ ÑÑ‚Ð¸Ð¼ route_id
            cursor.execute("SELECT order_id, order_data FROM orders WHERE status != 'archived'")
            orders = cursor.fetchall()

            for order in orders:
                try:
                    order_data = json.loads(order['order_data'])

                    # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ route_id
                    if order_data.get('route_id') == route_id:
                        old_name = order_data.get('route_name')
                        if old_name != new_route_name:
                            order_data['route_name'] = new_route_name

                            cursor.execute('''
                                UPDATE orders SET order_data = ?, updated_at = ?
                                WHERE order_id = ?
                            ''', (json.dumps(order_data, ensure_ascii=False),
                                  datetime.now().isoformat(),
                                  order['order_id']))

                            updated_order_ids.append(order['order_id'])
                            logger.info(f"Updated route_name for order {order['order_id']}: {old_name} -> {new_route_name}")

                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Error parsing order {order['order_id']}: {e}")
                    continue

            conn.commit()
            logger.info(f"Updated {len(updated_order_ids)} orders with new route_name for route {route_id}")

        except Exception as e:
            logger.error(f"Error updating orders route_name for route {route_id}: {e}")
        finally:
            conn.close()

        return updated_order_ids

    def update_orders_route_to_free(self, old_route_id: str) -> list:
        """
        ÐŸÐµÑ€ÐµÐ¼ÐµÑÑ‚Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ñ route_id Ð½Ð° 'free' Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚.
        Ð’Ñ‹Ð·Ñ‹Ð²Ð°ÐµÑ‚ÑÑ Ð¿Ñ€Ð¸ ÑƒÐ´Ð°Ð»ÐµÐ½Ð¸Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°.

        Args:
            old_route_id: ID ÑƒÐ´Ð°Ð»ÑÐµÐ¼Ð¾Ð³Ð¾ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°

        Returns:
            Ð¡Ð¿Ð¸ÑÐ¾Ðº order_id Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ñ‹Ñ… Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        updated_order_ids = []

        try:
            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ route_name Ð´Ð»Ñ 'free'
            cursor.execute("SELECT route_name FROM logistics_routes WHERE route_id = 'free'")
            row = cursor.fetchone()
            free_route_name = row['route_name'] if row else 'Ð¡Ð²Ð¾Ð±Ð¾Ð´Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ñ‹'

            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð²ÑÐµ Ð°ÐºÑ‚Ð¸Ð²Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ñ ÑÑ‚Ð¸Ð¼ route_id
            cursor.execute("SELECT order_id, order_data FROM orders WHERE status != 'archived'")
            orders = cursor.fetchall()

            for order in orders:
                try:
                    order_data = json.loads(order['order_data'])

                    # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ route_id
                    if order_data.get('route_id') == old_route_id:
                        order_data['route_id'] = 'free'
                        order_data['route_name'] = free_route_name

                        cursor.execute('''
                            UPDATE orders SET order_data = ?, updated_at = ?
                            WHERE order_id = ?
                        ''', (json.dumps(order_data, ensure_ascii=False),
                              datetime.now().isoformat(),
                              order['order_id']))

                        updated_order_ids.append(order['order_id'])
                        logger.info(f"Moved order {order['order_id']} from {old_route_id} to 'free'")

                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Error parsing order {order['order_id']}: {e}")
                    continue

            conn.commit()
            logger.info(f"Moved {len(updated_order_ids)} orders from route {old_route_id} to 'free'")

        except Exception as e:
            logger.error(f"Error moving orders from route {old_route_id}: {e}")
        finally:
            conn.close()

        return updated_order_ids

    def sync_all_orders_routes_from_clients(self, include_archived: bool = False) -> int:
        """
        ???????????????? route_id/route_name ? ??????? ?? ?????????? ?????? client_routes.

        Args:
            include_archived: ???????? ?? ???????? ??????.

        Returns:
            ?????????? ??????????? ???????.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        updated_count = 0

        try:
            # ????? ????????: normalized_any_client_id -> (route_id, route_name)
            cursor.execute(
                """
                SELECT
                    cr.client_id AS client_id,
                    cr.monolith_client_id AS monolith_client_id,
                    cr.route_id AS route_id,
                    COALESCE(lr.route_name, cr.route_id, 'free') AS route_name
                FROM client_routes cr
                LEFT JOIN logistics_routes lr ON cr.route_id = lr.route_id
                """
            )
            client_rows = cursor.fetchall()
            client_route_map = {}
            for row in client_rows:
                ids = [
                    str(row['client_id'] or '').strip(),
                    str(row['monolith_client_id'] or '').strip(),
                ]
                route_payload = (
                    str(row['route_id'] or 'free').strip() or 'free',
                    str(row['route_name'] or 'free').strip() or 'free'
                )
                for cid in ids:
                    if not cid:
                        continue
                    cid_norm = cid.lstrip('0') or cid
                    client_route_map[cid_norm] = route_payload

            if not client_route_map:
                return 0

            if include_archived:
                cursor.execute("SELECT order_id, order_data FROM orders")
            else:
                cursor.execute("SELECT order_id, order_data FROM orders WHERE status != 'archived'")
            orders = cursor.fetchall()

            for order in orders:
                try:
                    order_data = json.loads(order['order_data'])
                except Exception:
                    continue

                kunden_nr = str(order_data.get('kunden_nr', '')).strip()
                if not kunden_nr:
                    continue
                kunden_norm = kunden_nr.lstrip('0') or kunden_nr

                target = client_route_map.get(kunden_norm)
                if not target:
                    continue

                target_route_id, target_route_name = target
                current_route_id = str(order_data.get('route_id') or '').strip()
                current_route_name = str(order_data.get('route_name') or '').strip()

                if current_route_id == target_route_id and current_route_name == target_route_name:
                    continue

                order_data['route_id'] = target_route_id
                order_data['route_name'] = target_route_name

                cursor.execute(
                    "UPDATE orders SET order_data = ?, updated_at = ? WHERE order_id = ?",
                    (json.dumps(order_data, ensure_ascii=False), datetime.now().isoformat(), order['order_id'])
                )
                updated_count += 1

            if updated_count:
                conn.commit()
                logger.info(f"Synced routes in {updated_count} orders from client_routes")

        except Exception as e:
            logger.error(f"Error syncing order routes from client_routes: {e}")
        finally:
            conn.close()

        return updated_count

    def mark_client_reviewed(self, client_id: str) -> bool:
        """Ð¡Ð½ÑÑ‚ÑŒ Ð¼ÐµÑ‚ÐºÑƒ NEW Ñ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð° (Ð¿Ð¾ÑÐ»Ðµ Ð¿Ñ€Ð¾ÑÐ¼Ð¾Ñ‚Ñ€Ð°/Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸)"""
        conn = self.get_connection()
        try:
            conn.execute("UPDATE client_routes SET is_new = 0 WHERE client_id = ?", (client_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error marking client reviewed: {e}")
            return False
        finally:
            conn.close()

    def mark_recipe_reviewed(self, article_nr: str) -> bool:
        """Ð¡Ð½ÑÑ‚ÑŒ Ð¼ÐµÑ‚ÐºÑƒ NEW Ñ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð° (Ð¿Ð¾ÑÐ»Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ð¾Ð²)"""
        conn = self.get_connection()
        try:
            conn.execute("UPDATE recipes SET is_new = 0 WHERE article_nr = ?", (article_nr,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error marking recipe reviewed: {e}")
            return False
        finally:
            conn.close()

    def mark_all_clients_reviewed(self) -> int:
        """Ð¡Ð½ÑÑ‚ÑŒ Ð¼ÐµÑ‚ÐºÑƒ NEW ÑÐ¾ Ð²ÑÐµÑ… ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE client_routes SET is_new = 0 WHERE is_new = 1")
            count = cursor.rowcount
            conn.commit()
            return count
        except Exception as e:
            logger.error(f"Error marking all clients reviewed: {e}")
            return 0
        finally:
            conn.close()

    def mark_all_recipes_reviewed(self) -> int:
        """Ð¡Ð½ÑÑ‚ÑŒ Ð¼ÐµÑ‚ÐºÑƒ NEW ÑÐ¾ Ð²ÑÐµÑ… Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð²"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE recipes SET is_new = 0 WHERE is_new = 1")
            count = cursor.rowcount
            conn.commit()
            return count
        except Exception as e:
            logger.error(f"Error marking all recipes reviewed: {e}")
            return 0
        finally:
            conn.close()

    # ============================================
    # ÐžÐ¨Ð˜Ð‘ÐšÐ˜ Ð˜ Ð›ÐžÐ“Ð˜
    # ============================================
    def log_error(self, source: str, error_type: str, message: str):
        """Ð—Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ Ð¾ÑˆÐ¸Ð±ÐºÑƒ"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO errors (timestamp, source, error_type, message)
            VALUES (?, ?, ?, ?)
        ''', (datetime.now().isoformat(), source, error_type, message))

        conn.commit()
        conn.close()

    def get_errors(self, limit: int = 100) -> list:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¾ÑˆÐ¸Ð±ÐºÐ¸"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM errors ORDER BY timestamp DESC LIMIT ?', (limit,))
        rows = cursor.fetchall()

        errors = []
        for row in rows:
            errors.append({
                'timestamp': row['timestamp'],
                'source': row['source'],
                'type': row['error_type'],
                'message': row['message']
            })

        conn.close()
        return errors

    def clear_errors(self):
        """ÐžÑ‡Ð¸ÑÑ‚Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ð¾ÑˆÐ¸Ð±ÐºÐ¸"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM errors')
        conn.commit()
        conn.close()

    def log_message(self, level: str, source: str, message: str):
        """Ð—Ð°Ð¿Ð¸ÑÐ°Ñ‚ÑŒ Ð»Ð¾Ð³"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO logs (timestamp, level, source, message)
            VALUES (?, ?, ?, ?)
        ''', (datetime.now().isoformat(), level, source, message))

        conn.commit()
        conn.close()

    def get_logs(self, limit: int = 500) -> list:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð»Ð¾Ð³Ð¸"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?', (limit,))
        rows = cursor.fetchall()

        logs = []
        for row in rows:
            logs.append({
                'timestamp': row['timestamp'],
                'level': row['level'],
                'source': row['source'],
                'message': row['message']
            })

        conn.close()
        return logs

    # ============================================
    # Ð˜Ð¡Ð¢ÐžÐ Ð˜Ð¯ ÐŸÐ•Ð§ÐÐ¢Ð˜
    # ============================================
    def add_print_history(self, order_id: str, user_id: int, username: str,
                         label_language: str = None, boxes_count: int = None):
        """Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð·Ð°Ð¿Ð¸ÑÑŒ Ð² Ð¸ÑÑ‚Ð¾Ñ€Ð¸ÑŽ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO print_history (order_id, user_id, username, printed_at, label_language, boxes_count)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (order_id, user_id, username, datetime.now().isoformat(), label_language, boxes_count))

        conn.commit()
        conn.close()

    def get_print_history(self, limit: int = 1000, start_date: str = None, end_date: str = None) -> list:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¸ÑÑ‚Ð¾Ñ€Ð¸ÑŽ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸"""
        conn = self.get_connection()
        cursor = conn.cursor()

        query = 'SELECT * FROM print_history'
        params = []

        if start_date or end_date:
            conditions = []
            if start_date:
                conditions.append('printed_at >= ?')
                params.append(start_date)
            if end_date:
                conditions.append('printed_at <= ?')
                params.append(end_date)
            query += ' WHERE ' + ' AND '.join(conditions)

        query += ' ORDER BY printed_at DESC LIMIT ?'
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        history = []
        for row in rows:
            history.append({
                'print_id': row['print_id'],
                'order_id': row['order_id'],
                'user_id': row['user_id'],
                'username': row['username'],
                'printed_at': row['printed_at'],
                'label_language': row['label_language'],
                'boxes_count': row['boxes_count']
            })

        conn.close()
        return history

    def get_print_statistics(self, start_date: str = None, end_date: str = None) -> dict:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÑƒ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ Ð¿Ð¾ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑÐ¼"""
        conn = self.get_connection()
        cursor = conn.cursor()

        query = '''
            SELECT
                username,
                COUNT(*) as total_prints,
                SUM(CASE WHEN boxes_count > 0 THEN boxes_count ELSE 0 END) as total_boxes
            FROM print_history
        '''
        params = []

        if start_date or end_date:
            conditions = []
            if start_date:
                conditions.append('printed_at >= ?')
                params.append(start_date)
            if end_date:
                conditions.append('printed_at <= ?')
                params.append(end_date)
            query += ' WHERE ' + ' AND '.join(conditions)

        query += ' GROUP BY username ORDER BY total_prints DESC'

        cursor.execute(query, params)
        rows = cursor.fetchall()

        stats = []
        for row in rows:
            stats.append({
                'username': row['username'],
                'total_prints': row['total_prints'],
                'total_boxes': row['total_boxes'] or 0
            })

        conn.close()
        return stats

    def update_kunde_names_from_csv(self, kunden_dict: dict):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð¸Ð¼ÐµÐ½Ð° ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² Ð² ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ñ… Ð·Ð°ÐºÐ°Ð·Ð°Ñ… Ð¸Ð· ÑÐ¿Ñ€Ð°Ð²Ð¾Ñ‡Ð½Ð¸ÐºÐ°"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð²ÑÐµ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ñ Auftrag
            cursor.execute('''
                SELECT order_id, order_data FROM orders
            ''')
            rows = cursor.fetchall()

            updated_count = 0
            for row in rows:
                order_id = row['order_id']
                order_data = json.loads(row['order_data'])

                # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ ÐµÑÑ‚ÑŒ Ð»Ð¸ kunden_nr Ð¸ Ð½ÐµÑ‚ Ð»Ð¸ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ð¾Ð³Ð¾ kunde
                kunden_nr = order_data.get('kunden_nr')
                current_kunde = order_data.get('kunde')

                # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ ÐµÑÐ»Ð¸ kunde Ð¿ÑƒÑÑ‚Ð¾Ð¹ Ð¸Ð»Ð¸ ÑÑ‚Ð¾ fallback "Kunde XXXXX"
                if kunden_nr and (not current_kunde or current_kunde.startswith('Kunde ')):
                    # Ð˜Ñ‰ÐµÐ¼ Ð² ÑÐ¿Ñ€Ð°Ð²Ð¾Ñ‡Ð½Ð¸ÐºÐµ Ñ€Ð°Ð·Ð½Ñ‹Ð¼Ð¸ ÑÐ¿Ð¾ÑÐ¾Ð±Ð°Ð¼Ð¸
                    kunden_nr_str = str(kunden_nr).strip()
                    new_kunde = None

                    # Ð’Ð°Ñ€Ð¸Ð°Ð½Ñ‚ 1: Ð¿Ñ€ÑÐ¼Ð¾Ð¹ Ð¿Ð¾Ð¸ÑÐº
                    if kunden_nr_str in kunden_dict:
                        new_kunde = kunden_dict[kunden_nr_str]
                        logger.debug(f"Found kunde by direct match: {kunden_nr_str} -> {new_kunde}")

                    # Ð’Ð°Ñ€Ð¸Ð°Ð½Ñ‚ 2: Ð±ÐµÐ· Ð²ÐµÐ´ÑƒÑ‰Ð¸Ñ… Ð½ÑƒÐ»ÐµÐ¹
                    if not new_kunde and kunden_nr_str.isdigit():
                        kunden_nr_int = str(int(kunden_nr_str))
                        if kunden_nr_int in kunden_dict:
                            new_kunde = kunden_dict[kunden_nr_int]
                            logger.debug(f"Found kunde by int: {kunden_nr_int} -> {new_kunde}")

                    # Ð’Ð°Ñ€Ð¸Ð°Ð½Ñ‚ 3: Ñ Ð²ÐµÐ´ÑƒÑ‰Ð¸Ð¼Ð¸ Ð½ÑƒÐ»ÑÐ¼Ð¸ (ÐµÑÐ»Ð¸ Ð² CSV ÐµÑÑ‚ÑŒ leading zeros)
                    if not new_kunde and kunden_nr_str.isdigit():
                        kunden_nr_padded = kunden_nr_str.zfill(5)
                        if kunden_nr_padded in kunden_dict:
                            new_kunde = kunden_dict[kunden_nr_padded]
                            logger.debug(f"Found kunde by padded: {kunden_nr_padded} -> {new_kunde}")

                    if new_kunde:
                        order_data['kunde'] = new_kunde
                        cursor.execute('''
                            UPDATE orders
                            SET order_data = ?
                            WHERE order_id = ?
                        ''', (json.dumps(order_data, ensure_ascii=False), order_id))
                        updated_count += 1
                        logger.info(f"âœ… Updated kunde for {order_id}: {kunden_nr_str} -> {new_kunde}")
                    else:
                        logger.warning(f"âŒ No kunde found in CSV for order {order_id}, kunden_nr: {kunden_nr_str}")

            conn.commit()
            logger.info(f"Updated {updated_count} orders with kunde names from CSV")

        except Exception as e:
            logger.error(f"Error updating kunde names: {e}")
            conn.rollback()
        finally:
            conn.close()

    # ============================================
    # Ð•Ð–Ð•Ð”ÐÐ•Ð’ÐÐ«Ð• ÐžÐ¢Ð§Ð•Ð¢Ð« Ð¡ÐšÐ›ÐÐ”Ð (Ð˜ÐÐ’Ð•ÐÐ¢ÐÐ Ð˜Ð—ÐÐ¦Ð˜Ð¯)
    # ============================================
    def save_daily_stock_report(self, date: str, report_data: list) -> bool:
        """
        Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ð¾Ñ‚Ñ‡ÐµÑ‚ ÑÐºÐ»Ð°Ð´Ð° Ð·Ð° Ð´ÐµÐ½ÑŒ (Ð¼Ð°ÑÑÐ¾Ð²Ð¾Ðµ ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ðµ)

        Args:
            date: Ð”Ð°Ñ‚Ð° Ð¾Ñ‚Ñ‡ÐµÑ‚Ð° Ð² Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ðµ YYYY-MM-DD
            report_data: Ð¡Ð¿Ð¸ÑÐ¾Ðº ÑÐ»Ð¾Ð²Ð°Ñ€ÐµÐ¹ [{'article_nr': '05001', 'quantity': 10}, ...]

        Returns:
            True ÐµÑÐ»Ð¸ ÑƒÑÐ¿ÐµÑˆÐ½Ð¾ ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¾
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            for item in report_data:
                # Ð˜Ð¡ÐŸÐ ÐÐ’Ð›Ð•ÐÐ˜Ð•: Ð”Ð¾Ð¿Ð¾Ð»Ð½Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð°Ñ Ð½Ð¾Ñ€Ð¼Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ñ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð° (Ð½Ð° Ð²ÑÑÐºÐ¸Ð¹ ÑÐ»ÑƒÑ‡Ð°Ð¹)
                raw_art = str(item.get('article_nr', '')).strip()
                # Ð•ÑÐ»Ð¸ Ñ‡Ð¸ÑÐ»Ð¾, Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð½ÑƒÐ»Ð¸ Ð´Ð¾ 5 Ð·Ð½Ð°ÐºÐ¾Ð²
                article_nr = raw_art.zfill(5) if raw_art.isdigit() else raw_art

                quantity = float(item.get('quantity', 0))

                cursor.execute('''
                    INSERT OR REPLACE INTO daily_stock_reports (date, article_nr, quantity, updated_at)
                    VALUES (?, ?, ?, ?)
                ''', (date, article_nr, quantity, datetime.now().isoformat()))

            conn.commit()
            logger.info(f"Saved daily stock report for {date}: {len(report_data)} items (normalized)")
            return True

        except Exception as e:
            logger.error(f"Error saving daily stock report: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def get_daily_stock_report(self, date: str) -> list:
        """
        ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¾Ñ‚Ñ‡ÐµÑ‚ ÑÐºÐ»Ð°Ð´Ð° Ð·Ð° ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ (Ð¡ ÐŸÐ Ð˜ÐÐ£Ð”Ð˜Ð¢Ð•Ð›Ð¬ÐÐ«ÐœÐ˜ ÐÐ£Ð›Ð¯ÐœÐ˜)
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT article_nr, quantity, last_editor, updated_at
                FROM daily_stock_reports
                WHERE date = ?
                ORDER BY article_nr
            ''', (date,))

            rows = cursor.fetchall()
            report = []

            for row in rows:
                # --- Ð˜Ð¡ÐŸÐ ÐÐ’Ð›Ð•ÐÐ˜Ð•: Ð’ÐžÐ—Ð’Ð ÐÐ©ÐÐ•Ðœ ÐÐžÐ›Ð¬ ---
                raw_art = str(row['article_nr']).strip()
                art_nr = raw_art.zfill(5) if raw_art.isdigit() else raw_art
                # ------------------------------------

                report.append({
                    'article_nr': art_nr,
                    'quantity': row['quantity'],
                    'last_editor': row['last_editor'],
                    'updated_at': row['updated_at']
                })

            return report

        except Exception as e:
            logger.error(f"Error getting daily stock report: {e}")
            return []
        finally:
            conn.close()

    def get_stock_for_date(self, article_nr: str, date: str) -> float:
        """
        ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ðº ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½Ð¾Ð³Ð¾ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð° Ð½Ð° ÐºÐ¾Ð½ÐºÑ€ÐµÑ‚Ð½ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ

        Args:
            article_nr: ÐÐ¾Ð¼ÐµÑ€ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð°
            date: Ð”Ð°Ñ‚Ð° Ð² Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ðµ YYYY-MM-DD

        Returns:
            ÐšÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ Ð½Ð° ÑÐºÐ»Ð°Ð´Ðµ (0 ÐµÑÐ»Ð¸ Ð½ÐµÑ‚ Ð´Ð°Ð½Ð½Ñ‹Ñ…)
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # ÐÐ¾Ñ€Ð¼Ð°Ð»Ð¸Ð·ÑƒÐµÐ¼ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» Ð¿ÐµÑ€ÐµÐ´ Ð¿Ð¾Ð¸ÑÐºÐ¾Ð¼
            normalized_article = str(article_nr).strip()
            if normalized_article.isdigit():
                normalized_article = normalized_article.zfill(5)

            cursor.execute('''
                SELECT quantity
                FROM daily_stock_reports
                WHERE date = ? AND article_nr = ?
            ''', (date, normalized_article))

            row = cursor.fetchone()
            return float(row['quantity']) if row else 0.0

        except Exception as e:
            logger.error(f"Error getting stock for article {article_nr} on {date}: {e}")
            return 0.0
        finally:
            conn.close()

    def get_latest_stock_report_date(self) -> Optional[str]:
        """
        ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð´Ð°Ñ‚Ñƒ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÐµÐ³Ð¾ ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð½Ð¾Ð³Ð¾ Ð¾Ñ‚Ñ‡ÐµÑ‚Ð°

        Returns:
            Ð”Ð°Ñ‚Ð° Ð² Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ðµ YYYY-MM-DD Ð¸Ð»Ð¸ None
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT date
                FROM daily_stock_reports
                ORDER BY date DESC
                LIMIT 1
            ''')

            row = cursor.fetchone()
            return row['date'] if row else None

        except Exception as e:
            logger.error(f"Error getting latest stock report date: {e}")
            return None
        finally:
            conn.close()

    # ============================================
    # COMMUNICATION (CHAT/TASKS)
    # ============================================
    def get_comm_users(self) -> list:
        conn = self.get_connection()
        try:
            rows = conn.execute(
                """
                SELECT user_id, username,
                       COALESCE(NULLIF(display_name, ''), username) AS display_name,
                       role, warehouse_id
                FROM users
                ORDER BY COALESCE(NULLIF(display_name, ''), username)
                """
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def create_comm_dialog(self, created_by: int, title: str, participant_ids: list, is_group: bool = False) -> int:
        conn = self.get_connection()
        try:
            now = datetime.now().isoformat()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO comm_dialogs (title, is_group, created_by, created_at) VALUES (?, ?, ?, ?)",
                (title.strip() or 'Ð”Ð¸Ð°Ð»Ð¾Ð³', 1 if is_group else 0, int(created_by), now)
            )
            dialog_id = int(cur.lastrowid)
            member_ids = {int(created_by)}
            for uid in participant_ids or []:
                try:
                    member_ids.add(int(uid))
                except Exception:
                    continue
            for uid in member_ids:
                cur.execute(
                    "INSERT OR IGNORE INTO comm_dialog_members (dialog_id, user_id, added_at) VALUES (?, ?, ?)",
                    (dialog_id, uid, now)
                )
            conn.commit()
            return dialog_id
        finally:
            conn.close()

    def add_comm_dialog_participants(self, dialog_id: int, participant_ids: list) -> int:
        conn = self.get_connection()
        added = 0
        try:
            now = datetime.now().isoformat()
            cur = conn.cursor()
            for uid in participant_ids or []:
                try:
                    uid_i = int(uid)
                except Exception:
                    continue
                cur.execute(
                    "INSERT OR IGNORE INTO comm_dialog_members (dialog_id, user_id, added_at) VALUES (?, ?, ?)",
                    (int(dialog_id), uid_i, now)
                )
                if cur.rowcount > 0:
                    added += 1
            conn.commit()
            return added
        finally:
            conn.close()

    def is_comm_dialog_member(self, dialog_id: int, user_id: int) -> bool:
        conn = self.get_connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM comm_dialog_members WHERE dialog_id=? AND user_id=?",
                (int(dialog_id), int(user_id))
            ).fetchone()
            return bool(row)
        finally:
            conn.close()

    def get_comm_dialog_members(self, dialog_id: int) -> list:
        conn = self.get_connection()
        try:
            rows = conn.execute(
                "SELECT user_id FROM comm_dialog_members WHERE dialog_id=?",
                (int(dialog_id),)
            ).fetchall()
            return [int(r['user_id']) for r in rows]
        finally:
            conn.close()

    def get_comm_dialog_members_info(self, dialog_id: int) -> list:
        conn = self.get_connection()
        try:
            rows = conn.execute('''
                SELECT u.user_id, u.username,
                       COALESCE(NULLIF(u.display_name, ''), u.username) AS display_name,
                       u.role
                FROM comm_dialog_members dm
                JOIN users u ON u.user_id = dm.user_id
                WHERE dm.dialog_id = ?
                ORDER BY COALESCE(NULLIF(u.display_name, ''), u.username)
            ''', (int(dialog_id),)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_comm_dialogs_for_user(self, user_id: int) -> list:
        conn = self.get_connection()
        try:
            rows = conn.execute('''
                SELECT d.dialog_id, d.title, d.is_group, d.created_by, d.created_at,
                       MAX(m.created_at) AS last_message_at,
                       (SELECT message_text FROM comm_messages mm WHERE mm.dialog_id = d.dialog_id ORDER BY mm.created_at DESC LIMIT 1) AS last_message,
                       (SELECT COUNT(*) FROM comm_dialog_members dm WHERE dm.dialog_id = d.dialog_id) AS members_count
                FROM comm_dialogs d
                JOIN comm_dialog_members me ON me.dialog_id = d.dialog_id
                LEFT JOIN comm_messages m ON m.dialog_id = d.dialog_id
                WHERE me.user_id = ?
                GROUP BY d.dialog_id, d.title, d.is_group, d.created_by, d.created_at
                ORDER BY COALESCE(last_message_at, d.created_at) DESC
            ''', (int(user_id),)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_or_create_private_dialog(self, me_user_id: int, other_user_id: int) -> int:
        conn = self.get_connection()
        try:
            me = int(me_user_id)
            other = int(other_user_id)
            if me == other:
                return 0
            row = conn.execute('''
                SELECT d.dialog_id
                FROM comm_dialogs d
                JOIN comm_dialog_members m1 ON m1.dialog_id = d.dialog_id AND m1.user_id = ?
                JOIN comm_dialog_members m2 ON m2.dialog_id = d.dialog_id AND m2.user_id = ?
                WHERE d.is_group = 0
                  AND (SELECT COUNT(*) FROM comm_dialog_members x WHERE x.dialog_id = d.dialog_id) = 2
                ORDER BY d.dialog_id DESC
                LIMIT 1
            ''', (me, other)).fetchone()
            if row:
                return int(row['dialog_id'])
            other_name_row = conn.execute(
                "SELECT username, COALESCE(NULLIF(display_name, ''), username) AS display_name FROM users WHERE user_id = ?",
                (other,)
            ).fetchone()
            other_name = str(other_name_row['display_name']) if other_name_row else f"User {other}"
            now = datetime.now().isoformat()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO comm_dialogs (title, is_group, created_by, created_at) VALUES (?, 0, ?, ?)",
                (other_name, me, now)
            )
            dialog_id = int(cur.lastrowid)
            cur.execute(
                "INSERT OR IGNORE INTO comm_dialog_members (dialog_id, user_id, added_at) VALUES (?, ?, ?)",
                (dialog_id, me, now)
            )
            cur.execute(
                "INSERT OR IGNORE INTO comm_dialog_members (dialog_id, user_id, added_at) VALUES (?, ?, ?)",
                (dialog_id, other, now)
            )
            conn.commit()
            return dialog_id
        finally:
            conn.close()

    def get_comm_dialog_by_id(self, dialog_id: int) -> dict:
        conn = self.get_connection()
        try:
            row = conn.execute(
                "SELECT dialog_id, title, is_group, created_by, created_at FROM comm_dialogs WHERE dialog_id=?",
                (int(dialog_id),)
            ).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def leave_comm_dialog(self, dialog_id: int, user_id: int) -> dict:
        conn = self.get_connection()
        try:
            did = int(dialog_id)
            uid = int(user_id)
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM comm_dialog_members WHERE dialog_id=? AND user_id=?",
                (did, uid)
            )
            removed = cur.rowcount > 0
            members_left_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM comm_dialog_members WHERE dialog_id=?",
                (did,)
            ).fetchone()
            members_left = int(members_left_row['cnt']) if members_left_row else 0
            if members_left <= 0:
                cur.execute("DELETE FROM comm_message_reads WHERE message_id IN (SELECT message_id FROM comm_messages WHERE dialog_id=?)", (did,))
                cur.execute("DELETE FROM comm_messages WHERE dialog_id=?", (did,))
                cur.execute("DELETE FROM comm_dialogs WHERE dialog_id=?", (did,))
            conn.commit()
            return {'removed': removed, 'members_left': members_left}
        finally:
            conn.close()

    def delete_comm_dialog(self, dialog_id: int) -> bool:
        conn = self.get_connection()
        try:
            did = int(dialog_id)
            cur = conn.cursor()
            cur.execute("DELETE FROM comm_message_reads WHERE message_id IN (SELECT message_id FROM comm_messages WHERE dialog_id=?)", (did,))
            cur.execute("DELETE FROM comm_messages WHERE dialog_id=?", (did,))
            cur.execute("DELETE FROM comm_dialog_members WHERE dialog_id=?", (did,))
            cur.execute("DELETE FROM comm_dialogs WHERE dialog_id=?", (did,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_comm_messages(self, dialog_id: int, limit: int = 500, user_id: int = 0, before_message_id: int = 0) -> list:
        conn = self.get_connection()
        try:
            if int(before_message_id or 0) > 0:
                rows = conn.execute('''
                    SELECT * FROM (
                        SELECT m.message_id, m.dialog_id, m.sender_id, COALESCE(NULLIF(u.display_name, ''), u.username) AS sender_name,
                               m.message_text, m.created_at, m.edited_at,
                               CASE WHEN a.message_id IS NOT NULL THEN 1 ELSE 0 END AS has_attachment,
                               COALESCE(a.file_name, '') AS attachment_name,
                               COALESCE(a.mime_type, '') AS attachment_mime_type,
                               COALESCE(a.file_size, 0) AS attachment_size,
                               (
                                   SELECT COUNT(*)
                                   FROM comm_message_reads r
                                   WHERE r.message_id = m.message_id
                                     AND r.user_id != m.sender_id
                               ) AS read_by_count,
                               (
                                   SELECT COUNT(*)
                                   FROM comm_dialog_members dm
                                   WHERE dm.dialog_id = m.dialog_id
                                     AND dm.user_id != m.sender_id
                               ) AS recipients_count,
                               CASE
                                   WHEN ? > 0 AND EXISTS (
                                       SELECT 1
                                       FROM comm_message_reads rr
                                       WHERE rr.message_id = m.message_id
                                         AND rr.user_id = ?
                                   ) THEN 1 ELSE 0
                               END AS is_read_by_me
                        FROM comm_messages m
                        LEFT JOIN users u ON u.user_id = m.sender_id
                        LEFT JOIN comm_message_attachments a ON a.message_id = m.message_id
                        WHERE m.dialog_id = ?
                          AND m.message_id < ?
                        ORDER BY m.message_id DESC
                        LIMIT ?
                    ) q
                    ORDER BY q.message_id ASC
                ''', (int(user_id or 0), int(user_id or 0), int(dialog_id), int(before_message_id), int(limit))).fetchall()
            else:
                rows = conn.execute('''
                    SELECT * FROM (
                SELECT m.message_id, m.dialog_id, m.sender_id, COALESCE(NULLIF(u.display_name, ''), u.username) AS sender_name,
                       m.message_text, m.created_at, m.edited_at,
                       CASE WHEN a.message_id IS NOT NULL THEN 1 ELSE 0 END AS has_attachment,
                       COALESCE(a.file_name, '') AS attachment_name,
                       COALESCE(a.mime_type, '') AS attachment_mime_type,
                       COALESCE(a.file_size, 0) AS attachment_size,
                       (
                           SELECT COUNT(*)
                           FROM comm_message_reads r
                           WHERE r.message_id = m.message_id
                             AND r.user_id != m.sender_id
                               ) AS read_by_count,
                               (
                                   SELECT COUNT(*)
                                   FROM comm_dialog_members dm
                                   WHERE dm.dialog_id = m.dialog_id
                                     AND dm.user_id != m.sender_id
                               ) AS recipients_count,
                               CASE
                                   WHEN ? > 0 AND EXISTS (
                                       SELECT 1
                                       FROM comm_message_reads rr
                                       WHERE rr.message_id = m.message_id
                                         AND rr.user_id = ?
                                   ) THEN 1 ELSE 0
                               END AS is_read_by_me
                FROM comm_messages m
                LEFT JOIN users u ON u.user_id = m.sender_id
                LEFT JOIN comm_message_attachments a ON a.message_id = m.message_id
                WHERE m.dialog_id = ?
                        ORDER BY m.message_id DESC
                        LIMIT ?
                    ) q
                    ORDER BY q.message_id ASC
                ''', (int(user_id or 0), int(user_id or 0), int(dialog_id), int(limit))).fetchall()
            result = []
            for r in rows:
                obj = dict(r)
                recipients_count = int(obj.get('recipients_count') or 0)
                read_by_count = int(obj.get('read_by_count') or 0)
                obj['seen_by_all'] = 1 if recipients_count <= 0 or read_by_count >= recipients_count else 0
                result.append(obj)
            return result
        finally:
            conn.close()

    def create_comm_message(self, dialog_id: int, sender_id: int, message_text: str) -> dict:
        conn = self.get_connection()
        try:
            now = datetime.now().isoformat()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO comm_messages (dialog_id, sender_id, message_text, created_at) VALUES (?, ?, ?, ?)",
                (int(dialog_id), int(sender_id), str(message_text).strip(), now)
            )
            message_id = int(cur.lastrowid)
            cur.execute(
                "INSERT OR IGNORE INTO comm_message_reads (message_id, user_id, read_at) VALUES (?, ?, ?)",
                (message_id, int(sender_id), now)
            )
            conn.commit()
            row = conn.execute('''
                SELECT m.message_id, m.dialog_id, m.sender_id, COALESCE(NULLIF(u.display_name, ''), u.username) AS sender_name,
                       m.message_text, m.created_at, m.edited_at,
                       0 AS has_attachment,
                       '' AS attachment_name,
                       '' AS attachment_mime_type,
                       0 AS attachment_size,
                       0 AS read_by_count,
                       0 AS recipients_count,
                       1 AS is_read_by_me,
                       0 AS seen_by_all
                FROM comm_messages m
                LEFT JOIN users u ON u.user_id = m.sender_id
                WHERE m.message_id = ?
            ''', (message_id,)).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def create_comm_attachment_message(self, dialog_id: int, sender_id: int, file_name: str, mime_type: str, file_data: bytes) -> dict:
        conn = self.get_connection()
        try:
            now = datetime.now().isoformat()
            data = bytes(file_data or b'')
            if not data:
                return {}
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO comm_messages (dialog_id, sender_id, message_text, created_at) VALUES (?, ?, ?, ?)",
                (int(dialog_id), int(sender_id), '', now)
            )
            message_id = int(cur.lastrowid)
            cur.execute(
                "INSERT INTO comm_message_attachments (message_id, file_name, mime_type, file_size, file_data, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    message_id,
                    str(file_name or 'file.bin').strip()[:260],
                    str(mime_type or '').strip()[:128],
                    int(len(data)),
                    sqlite3.Binary(data),
                    now
                )
            )
            cur.execute(
                "INSERT OR IGNORE INTO comm_message_reads (message_id, user_id, read_at) VALUES (?, ?, ?)",
                (message_id, int(sender_id), now)
            )
            conn.commit()
            row = conn.execute('''
                SELECT m.message_id, m.dialog_id, m.sender_id, COALESCE(NULLIF(u.display_name, ''), u.username) AS sender_name,
                       m.message_text, m.created_at, m.edited_at,
                       1 AS has_attachment,
                       COALESCE(a.file_name, '') AS attachment_name,
                       COALESCE(a.mime_type, '') AS attachment_mime_type,
                       COALESCE(a.file_size, 0) AS attachment_size,
                       0 AS read_by_count,
                       0 AS recipients_count,
                       1 AS is_read_by_me,
                       0 AS seen_by_all
                FROM comm_messages m
                LEFT JOIN users u ON u.user_id = m.sender_id
                LEFT JOIN comm_message_attachments a ON a.message_id = m.message_id
                WHERE m.message_id = ?
            ''', (message_id,)).fetchone()
            return dict(row) if row else {}
        finally:
            conn.close()

    def get_comm_attachment(self, message_id: int) -> dict:
        conn = self.get_connection()
        try:
            row = conn.execute('''
                SELECT a.message_id, a.file_name, a.mime_type, a.file_size, a.file_data, m.dialog_id
                FROM comm_message_attachments a
                JOIN comm_messages m ON m.message_id = a.message_id
                WHERE a.message_id = ?
            ''', (int(message_id),)).fetchone()
            if not row:
                return {}
            d = dict(row)
            d['file_data'] = bytes(d.get('file_data') or b'')
            return d
        finally:
            conn.close()

    def mark_comm_dialog_read(self, dialog_id: int, user_id: int) -> list:
        conn = self.get_connection()
        try:
            now = datetime.now().isoformat()
            rows = conn.execute('''
                SELECT m.message_id
                FROM comm_messages m
                WHERE m.dialog_id = ?
                  AND m.sender_id != ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM comm_message_reads r
                      WHERE r.message_id = m.message_id
                        AND r.user_id = ?
                  )
            ''', (int(dialog_id), int(user_id), int(user_id))).fetchall()
            message_ids = [int(r['message_id']) for r in rows]
            if message_ids:
                conn.executemany(
                    "INSERT OR IGNORE INTO comm_message_reads (message_id, user_id, read_at) VALUES (?, ?, ?)",
                    [(mid, int(user_id), now) for mid in message_ids]
                )
                conn.commit()
            return message_ids
        finally:
            conn.close()

    def get_comm_message_read_state(self, message_id: int) -> dict:
        conn = self.get_connection()
        try:
            row = conn.execute('''
                SELECT m.message_id,
                       (
                           SELECT COUNT(*)
                           FROM comm_message_reads r
                           WHERE r.message_id = m.message_id
                             AND r.user_id != m.sender_id
                       ) AS read_by_count,
                       (
                           SELECT COUNT(*)
                           FROM comm_dialog_members dm
                           WHERE dm.dialog_id = m.dialog_id
                             AND dm.user_id != m.sender_id
                       ) AS recipients_count
                FROM comm_messages m
                WHERE m.message_id = ?
            ''', (int(message_id),)).fetchone()
            if not row:
                return {}
            d = dict(row)
            recipients_count = int(d.get('recipients_count') or 0)
            read_by_count = int(d.get('read_by_count') or 0)
            d['seen_by_all'] = 1 if recipients_count <= 0 or read_by_count >= recipients_count else 0
            return d
        finally:
            conn.close()

    def _get_comm_task_by_id_conn(self, conn, task_id: int) -> dict:
        row = conn.execute('''
            SELECT t.task_id, t.title, t.description, t.assigned_to,
                   COALESCE(NULLIF(ua.display_name, ''), ua.username) AS assigned_to_name,
                   t.created_by, COALESCE(NULLIF(uc.display_name, ''), uc.username) AS created_by_name, t.deadline_date,
                   t.status, t.created_at, t.updated_at,
                   COALESCE((
                       SELECT GROUP_CONCAT(a.user_id)
                       FROM comm_task_assignees a
                       WHERE a.task_id = t.task_id
                   ), '') AS assignee_ids_csv,
                   COALESCE((
                       SELECT GROUP_CONCAT(COALESCE(NULLIF(u.display_name, ''), u.username), ', ')
                       FROM comm_task_assignees a
                       JOIN users u ON u.user_id = a.user_id
                       WHERE a.task_id = t.task_id
                   ), '') AS assignees_display,
                   COALESCE((
                       SELECT GROUP_CONCAT(w.user_id)
                       FROM comm_task_watchers w
                       WHERE w.task_id = t.task_id
                   ), '') AS watcher_ids_csv,
                   COALESCE((
                       SELECT GROUP_CONCAT(COALESCE(NULLIF(u.display_name, ''), u.username), ', ')
                       FROM comm_task_watchers w
                       JOIN users u ON u.user_id = w.user_id
                       WHERE w.task_id = t.task_id
                   ), '') AS watchers_display
            FROM comm_tasks t
            LEFT JOIN users ua ON ua.user_id = t.assigned_to
            LEFT JOIN users uc ON uc.user_id = t.created_by
            WHERE t.task_id = ?
        ''', (int(task_id),)).fetchone()
        if not row:
            return {}
        task = dict(row)
        task['assignee_ids'] = [int(x) for x in str(task.pop('assignee_ids_csv') or '').split(',') if x.strip().isdigit()]
        task['watcher_ids'] = [int(x) for x in str(task.pop('watcher_ids_csv') or '').split(',') if x.strip().isdigit()]
        return task

    def get_comm_tasks_for_user(self, user_id: int, role: str) -> list:
        conn = self.get_connection()
        try:
            rows = conn.execute('''
                SELECT DISTINCT t.task_id
                FROM comm_tasks t
                LEFT JOIN comm_task_assignees a ON a.task_id = t.task_id
                LEFT JOIN comm_task_watchers w ON w.task_id = t.task_id
                WHERE t.created_by = ?
                   OR a.user_id = ?
                   OR w.user_id = ?
                ORDER BY CASE t.status WHEN 'new' THEN 1 WHEN 'in_progress' THEN 2 WHEN 'done' THEN 3 ELSE 4 END,
                         COALESCE(t.deadline_date, '9999-12-31'),
                         t.created_at DESC
            ''', (int(user_id), int(user_id), int(user_id))).fetchall()
            return [self._get_comm_task_by_id_conn(conn, int(r['task_id'])) for r in rows]
        finally:
            conn.close()

    def create_comm_task(self, title: str, description: str, assignee_ids: list, created_by: int, deadline_date: str, watcher_ids: list = None) -> dict:
        conn = self.get_connection()
        try:
            now = datetime.now().isoformat()
            assignees = []
            for uid in assignee_ids or []:
                try:
                    assignees.append(int(uid))
                except Exception:
                    continue
            assignees = sorted(set(assignees))
            if not assignees:
                return {}
            watchers = []
            for uid in watcher_ids or []:
                try:
                    watchers.append(int(uid))
                except Exception:
                    continue
            watchers = sorted(set(watchers))
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO comm_tasks (title, description, assigned_to, created_by, deadline_date, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'new', ?, ?)
            ''', (str(title).strip(), str(description or '').strip(), int(assignees[0]), int(created_by),
                  (str(deadline_date).strip() or None), now, now))
            task_id = int(cur.lastrowid)
            cur.executemany(
                "INSERT OR IGNORE INTO comm_task_assignees (task_id, user_id, added_at) VALUES (?, ?, ?)",
                [(task_id, int(uid), now) for uid in assignees]
            )
            cur.executemany(
                "INSERT OR IGNORE INTO comm_task_watchers (task_id, user_id, added_at) VALUES (?, ?, ?)",
                [(task_id, int(uid), now) for uid in watchers]
            )
            conn.commit()
            return self._get_comm_task_by_id_conn(conn, task_id)
        finally:
            conn.close()

    def get_comm_task_participants(self, task_id: int) -> list:
        conn = self.get_connection()
        try:
            rows = conn.execute('''
                SELECT created_by AS user_id
                FROM comm_tasks
                WHERE task_id = ?
                UNION
                SELECT user_id
                FROM comm_task_assignees
                WHERE task_id = ?
                UNION
                SELECT user_id
                FROM comm_task_watchers
                WHERE task_id = ?
            ''', (int(task_id), int(task_id), int(task_id))).fetchall()
            return [int(r['user_id']) for r in rows]
        finally:
            conn.close()

    def can_user_update_comm_task(self, task_id: int, user_id: int) -> bool:
        conn = self.get_connection()
        try:
            row = conn.execute('''
                SELECT 1
                FROM comm_tasks t
                LEFT JOIN comm_task_assignees a ON a.task_id = t.task_id
                WHERE t.task_id = ?
                  AND (t.created_by = ? OR a.user_id = ?)
                LIMIT 1
            ''', (int(task_id), int(user_id), int(user_id))).fetchone()
            return bool(row)
        finally:
            conn.close()

    def update_comm_task_status(self, task_id: int, status: str) -> dict:
        allowed = {'new', 'in_progress', 'done'}
        st = str(status or '').strip()
        if st not in allowed:
            st = 'new'
        conn = self.get_connection()
        try:
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE comm_tasks SET status=?, updated_at=? WHERE task_id=?",
                (st, now, int(task_id))
            )
            conn.commit()
            return self._get_comm_task_by_id_conn(conn, int(task_id))
        finally:
            conn.close()
