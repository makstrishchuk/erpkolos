#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WISO GOLABEL - Ð•Ð”Ð˜ÐÐ«Ð™ Ð¡Ð•Ð Ð’Ð•Ð 
ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ð²ÑÐµÑ… Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ð¹: Ð°Ð´Ð¼Ð¸Ð½, Ð¾Ð¿ÐµÑ€Ð°Ñ‚Ð¾Ñ€, ÑÐºÐ»Ð°Ð´Ñ‹
Ð¡ Ð¿Ð¾Ð»Ð½Ð¾Ð¹ Ð°Ð²Ñ‚Ð¾Ñ€Ð¸Ð·Ð°Ñ†Ð¸ÐµÐ¹ Ð¸ ÑƒÐ¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸ÐµÐ¼ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑÐ¼Ð¸
"""

import asyncio
import websockets
import json
import sqlite3
import hashlib
import secrets
import os
import math
import time
import shutil
import sys
import functools
import base64
import smtplib
import ssl
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
import logging
from logging.handlers import TimedRotatingFileHandler
from typing import Dict, Set, Optional, List, Tuple
from dataclasses import dataclass
from collections import defaultdict, deque
from email.message import EmailMessage
# import requests  # Ð’Ñ€ÐµÐ¼ÐµÐ½Ð½Ð¾ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¾ - ÑƒÑÑ‚Ð°Ð½Ð¾Ð²Ð¸Ñ‚Ðµ Ñ‡ÐµÑ€ÐµÐ·: python -m pip install requests
# from lieferschein_monitor import LieferscheinMonitor  # REMOVED â€” Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ð² rechnung_monitor
# from pdf_parser import LieferscheinPDFParser
# from auftrag_monitor import AuftragMonitor  # DEPRECATED: Replaced by CSV monitor
# from auftrag_parser import AuftragPDFParser  # DEPRECATED: Replaced by CSV monitor
from csv_monitor import WisoCSVMonitor  # NEW: WISO ERP CSV import
from api_order_monitor import ApiOrderMonitor  # NEW: Monolith API order monitor
from rechnung_monitor import RechnungMonitor
import threading
from kunden_monitor import KundenCSVMonitor
# Backend modules
from backend.database import Database  # Extracted Database module
from backend.resource_manager import ResourceManager  # Extracted Resource Manager
from backend.logistics_manager import LogisticsManager  # Extracted Logistics Manager
from backend.stock_manager import VirtualStockManager  # Extracted Stock Manager
from backend.production_planner import ProductionPlanner  # Extracted Production Planner
from backend.zutaten_v2.api import ZutatenAPIHandlers, get_zutaten_message_handlers  # Zutaten V2 LMIV

# ============================================
# ÐÐÐ¡Ð¢Ð ÐžÐ™ÐšÐ˜
# ============================================
DB_PATH = Path(__file__).parent / "wiso_golabel.db"
AUDIT_DB_PATH = Path(__file__).parent / "wiso_golabel_audit.db"
# UNC Ð¿ÑƒÑ‚ÑŒ Ðº Ð¿Ð°Ð¿ÐºÐµ Lieferscheine Ð½Ð° ÑÐµÑ€Ð²ÐµÑ€Ðµ
LIEFERSCHEIN_FOLDER = Path(r"\\server01\DATA\WISO_GOLABEL\Lieferscheine")
# UNC Ð¿ÑƒÑ‚ÑŒ Ðº Ð¿Ð°Ð¿ÐºÐµ AuftragsbestÃ¤tigung (DEPRECATED - Ð·Ð°Ð¼ÐµÐ½ÐµÐ½Ð¾ Ð½Ð° CSV)
# AUFTRAG_FOLDER = Path(r"\\server01\DATA\WISO_GOLABEL\Auftrag")
# NEW: CSV Ñ„Ð°Ð¹Ð» ÑÐºÑÐ¿Ð¾Ñ€Ñ‚Ð° Ð·Ð°ÐºÐ°Ð·Ð¾Ð² Ð¸Ð· WISO ERP
WISO_CSV_PATH = Path(r"\\server01\DATA\WISO_GOLABEL\bestellung\export.csv")
# UNC Ð¿ÑƒÑ‚ÑŒ Ðº Ð¿Ð°Ð¿ÐºÐµ Rechnung
RECHNUNG_FOLDER = Path(r"\\server01\DATA\WISO_GOLABEL\Rechnung")
RECHNUNG_OUTPUT_FOLDER = Path(r"\\server01\DATA\WISO_GOLABEL\Rechnung\Processed")
KUNDEN_CSV_PATH = Path(r"\\server01\DATA\WISO_GOLABEL\kunden\export.csv")
# Backup paths
SYSTEM_BACKUP_SOURCE = Path(r"\\server01\DATA\Maks\wiso_golabel")
DOCUMENTS_BACKUP_SOURCE = Path(r"\\server01\DATA\WISO_GOLABEL")
BACKUP_ROOT_PATH = Path(r"\\server01\DATA\Maks\backup")
# Monolith API Ð´Ð»Ñ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
MONOLITH_API_URL = "https://api.monolith-gruppe.de/api/ZolotojKolos/getAllOrders/5/csv"
HOST = "0.0.0.0"
PORT = 8080

# FTP ÐºÐ¾Ð½Ñ„Ð¸Ð³ÑƒÑ€Ð°Ñ†Ð¸Ñ Ð´Ð»Ñ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÐºÐ¸ ÑÑ‡ÐµÑ‚Ð¾Ð² (Ð±ÑƒÐ´ÐµÑ‚ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐ½Ð¾ Ð¿Ð¾Ð·Ð¶Ðµ)
FTP_CONFIG = {
    'enabled': False,  # Ð’ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ ÐºÐ¾Ð³Ð´Ð° Ð¿Ð¾Ð»ÑƒÑ‡Ð¸Ð¼ Ð´Ð°Ð½Ð½Ñ‹Ðµ
    'host': '',
    'port': 21,
    'user': '',
    'password': '',
    'remote_path': ''
}

# Email/PDF for warehouse shipment notice (customer-facing PDF in German)
ORDER_EMAIL_CONFIG = {
    # Test mode: send to fixed mailbox instead of client email
    'test_mode': os.getenv('ORDER_EMAIL_TEST_MODE', '0').strip() == '1',
    'test_recipient': os.getenv('ORDER_EMAIL_TEST_RECIPIENT', '').strip(),
    # SMTP settings (configure via env)
    'smtp_host': os.getenv('ORDER_EMAIL_SMTP_HOST', 'localhost').strip(),
    'smtp_port': int(os.getenv('ORDER_EMAIL_SMTP_PORT', '25').strip() or '25'),
    'smtp_user': os.getenv('ORDER_EMAIL_SMTP_USER', '').strip(),
    'smtp_password': os.getenv('ORDER_EMAIL_SMTP_PASSWORD', '').strip(),
    'smtp_starttls': os.getenv('ORDER_EMAIL_SMTP_STARTTLS', '0').strip() == '1',
    'smtp_ssl': os.getenv('ORDER_EMAIL_SMTP_SSL', '0').strip() == '1',
    'smtp_tls_verify': os.getenv('ORDER_EMAIL_SMTP_TLS_VERIFY', '1').strip() == '1',
    'from_email': os.getenv('ORDER_EMAIL_FROM', '').strip(),
}

# Admin password for viewing user action audit in Settings > Admin.
# Can be overridden via environment variable on server.
ADMIN_AUDIT_PASSWORD = os.getenv('WISO_ADMIN_AUDIT_PASSWORD', 'LinkinPark2131').strip() or 'LinkinPark2131'

# ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ° Ð»Ð¾Ð³Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ
def _try_fix_mojibake(text):
    """Best-effort fixer for UTF-8 text decoded with wrong single-byte codec."""
    if not isinstance(text, str):
        return text
    def _noise_score(s: str) -> int:
        # Lower is better. Penalize classic mojibake markers and C1 controls.
        markers = "ÐÑÃÂâœžš¢"
        noise = sum(s.count(ch) for ch in markers)
        noise += sum(3 for ch in s if 0x80 <= ord(ch) <= 0x9F)
        # Reward real Cyrillic output.
        cyr = sum(1 for ch in s if ('\u0400' <= ch <= '\u04FF'))
        return noise - cyr

    best = text
    best_score = _noise_score(text)

    for src_enc in ('latin1', 'cp1252'):
        for enc_err in ('strict', 'ignore'):
            try:
                raw = text.encode(src_enc, errors=enc_err)
            except Exception:
                continue
            for dec_err in ('strict', 'replace', 'ignore'):
                try:
                    cand = raw.decode('utf-8', errors=dec_err)
                except Exception:
                    continue
                score = _noise_score(cand)
                if score < best_score:
                    best = cand
                    best_score = score

    return best


class MojibakeFixFilter(logging.Filter):
    def filter(self, record):
        try:
            if isinstance(record.msg, str):
                record.msg = _try_fix_mojibake(record.msg)
            if record.args:
                if isinstance(record.args, tuple):
                    record.args = tuple(_try_fix_mojibake(a) if isinstance(a, str) else a for a in record.args)
                elif isinstance(record.args, dict):
                    record.args = {
                        k: (_try_fix_mojibake(v) if isinstance(v, str) else v)
                        for k, v in record.args.items()
                    }
        except Exception:
            pass
        return True


logging.basicConfig(
    level=logging.INFO,  # Ð¡Ñ‚Ð°Ð½Ð´Ð°Ñ€Ñ‚Ð½Ñ‹Ð¹ ÑƒÑ€Ð¾Ð²ÐµÐ½ÑŒ Ð»Ð¾Ð³Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        TimedRotatingFileHandler(
            'server_unified.log',
            when='W0',           # weekly rotation (Monday)
            interval=1,
            backupCount=1,       # keep only current + previous week
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Apply mojibake fixer globally so file, console and GUI handlers see repaired text.
_mojibake_filter = MojibakeFixFilter()
logging.getLogger().addFilter(_mojibake_filter)
for _h in logging.getLogger().handlers:
    _h.addFilter(_mojibake_filter)

# ÐžÑ‚ÐºÐ»ÑŽÑ‡Ð°ÐµÐ¼ ÑÐ¿Ð°Ð¼ Ð¾Ñ‚ Ð±Ð¸Ð±Ð»Ð¸Ð¾Ñ‚ÐµÐºÐ¸ websockets Ð¿Ñ€Ð¸ Ð¾Ð±Ñ‹Ñ‡Ð½Ñ‹Ñ… Ñ€Ð°Ð·Ñ€Ñ‹Ð²Ð°Ñ… ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ñ
# (WinError 121 - Ñ‚Ð°Ð¹Ð¼Ð°ÑƒÑ‚ ÑÐµÐ¼Ð°Ñ„Ð¾Ñ€Ð° - ÑÑ‚Ð¾ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ð¾Ðµ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°)
logging.getLogger('websockets').setLevel(logging.CRITICAL)
logging.getLogger('websockets.protocol').setLevel(logging.CRITICAL)
logging.getLogger('websockets.legacy.protocol').setLevel(logging.CRITICAL)

# VirtualStockManager moved to backend/stock_manager.py

# WooCommerce API
WOOCOMMERCE_CONFIG = {
    'url': 'https://wiso24.com',
    'consumer_key': 'ck_your_key_here',
    'consumer_secret': 'cs_your_secret_here'
}

# ============================================
# ÐœÐžÐ”Ð•Ð›Ð˜ Ð”ÐÐÐÐ«Ð¥
# ============================================
@dataclass
class User:
    user_id: int
    username: str
    role: str  # 'admin', 'operator', 'warehouse'
    warehouse_id: Optional[str] = None
    password_hash: str = ''
    created_at: str = ''
    last_login: Optional[str] = None
    permissions: str = ''  # Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð¿Ñ€Ð°Ð² Ñ‡ÐµÑ€ÐµÐ· Ð·Ð°Ð¿ÑÑ‚ÑƒÑŽ: 'admin,orders,warehouse,logistics,production'

@dataclass
class Session:
    session_id: str
    user_id: int
    username: str
    role: str
    warehouse_id: Optional[str]
    websocket: websockets.WebSocketServerProtocol
    connected_at: str
    permissions: str = ''  # Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð¿Ñ€Ð°Ð² Ñ‡ÐµÑ€ÐµÐ· Ð·Ð°Ð¿ÑÑ‚ÑƒÑŽ

# Database class moved to backend/database.py

# ============================================
# ÐœÐ•ÐÐ•Ð”Ð–Ð•Ð  Ð¡Ð•Ð¡Ð¡Ð˜Ð™
# ============================================
class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.admin_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.operator_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.warehouse_clients: Dict[str, Set[websockets.WebSocketServerProtocol]] = {}

    def create_session(self, user: User, websocket: websockets.WebSocketServerProtocol) -> str:
        """Ð¡Ð¾Ð·Ð´Ð°Ñ‚ÑŒ ÑÐµÑÑÐ¸ÑŽ"""
        session_id = secrets.token_urlsafe(32)

        session = Session(
            session_id=session_id,
            user_id=user.user_id,
            username=user.username,
            role=user.role,
            warehouse_id=user.warehouse_id,
            websocket=websocket,
            connected_at=datetime.now().isoformat(),
            permissions=user.permissions
        )

        self.sessions[session_id] = session

        # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð² ÑÐ¾Ð¾Ñ‚Ð²ÐµÑ‚ÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
        if user.role == 'admin':
            self.admin_clients.add(websocket)
        elif user.role == 'operator':
            self.operator_clients.add(websocket)
        elif user.role == 'warehouse':
            if user.warehouse_id not in self.warehouse_clients:
                self.warehouse_clients[user.warehouse_id] = set()
            self.warehouse_clients[user.warehouse_id].add(websocket)

        logger.info(f"ÐÐ¾Ð²Ð°Ñ ÑÐµÑÑÐ¸Ñ: {user.username} ({user.role})")
        return session_id

    def remove_session(self, websocket: websockets.WebSocketServerProtocol):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÑÐµÑÑÐ¸ÑŽ"""
        session_to_remove = None

        for session_id, session in self.sessions.items():
            if session.websocket == websocket:
                session_to_remove = session_id
                break

        if session_to_remove:
            session = self.sessions[session_to_remove]

            # Ð£Ð´Ð°Ð»ÑÐµÐ¼ Ð¸Ð· ÑÐ¿Ð¸ÑÐºÐ¾Ð² ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
            if session.role == 'admin':
                self.admin_clients.discard(websocket)
            elif session.role == 'operator':
                self.operator_clients.discard(websocket)
            elif session.role == 'warehouse' and session.warehouse_id:
                if session.warehouse_id in self.warehouse_clients:
                    self.warehouse_clients[session.warehouse_id].discard(websocket)

            del self.sessions[session_to_remove]
            logger.info(f"Ð¡ÐµÑÑÐ¸Ñ Ð·Ð°ÐºÑ€Ñ‹Ñ‚Ð°: {session.username}")

    def get_session(self, websocket: websockets.WebSocketServerProtocol) -> Optional[Session]:
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÑÐµÑÑÐ¸ÑŽ Ð¿Ð¾ WebSocket"""
        for session in self.sessions.values():
            if session.websocket == websocket:
                return session
        return None

    async def _safe_broadcast(self, clients: set, message_json: str):
        """Ð‘ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð°Ñ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÐºÐ° Ñ Ð¾Ñ‡Ð¸ÑÑ‚ÐºÐ¾Ð¹ Ð¼Ñ‘Ñ€Ñ‚Ð²Ñ‹Ñ… ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ð¹."""
        if not clients:
            return
        dead = set()
        results = await asyncio.gather(
            *[client.send(message_json) for client in clients],
            return_exceptions=True
        )
        for client, result in zip(list(clients), results):
            if isinstance(result, Exception):
                dead.add(client)
        if dead:
            clients -= dead
            # Ð¢Ð°ÐºÐ¶Ðµ ÑƒÐ´Ð°Ð»ÑÐµÐ¼ ÑÐµÑÑÐ¸Ð¸ Ð¼Ñ‘Ñ€Ñ‚Ð²Ñ‹Ñ… ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
            for ws in dead:
                self.remove_session(ws)
            logger.info(f"Removed {len(dead)} dead websocket connections")

    async def broadcast_to_role(self, role: str, message: dict):
        """ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð²ÑÐµÐ¼ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑÐ¼ Ñ Ð¾Ð¿Ñ€ÐµÐ´ÐµÐ»ÐµÐ½Ð½Ð¾Ð¹ Ñ€Ð¾Ð»ÑŒÑŽ"""
        targets = set()

        if role == 'admin':
            targets = self.admin_clients
        elif role == 'operator':
            targets = self.operator_clients
        elif role == 'warehouse':
            for clients in self.warehouse_clients.values():
                targets.update(clients)

        await self._safe_broadcast(targets, json.dumps(message))

    async def broadcast_to_admins(self, message: dict):
        """ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð²ÑÐµÐ¼ Ð°Ð´Ð¼Ð¸Ð½Ð°Ð¼"""
        await self._safe_broadcast(self.admin_clients, json.dumps(message))

    async def broadcast_to_operators(self, message: dict):
        """ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð²ÑÐµÐ¼ Ð¾Ð¿ÐµÑ€Ð°Ñ‚Ð¾Ñ€Ð°Ð¼"""
        await self._safe_broadcast(self.operator_clients, json.dumps(message))

    async def broadcast_to_warehouse(self, warehouse_id: str, message: dict):
        """ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð²ÑÐµÐ¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼ ÑÐºÐ»Ð°Ð´Ð°"""
        if warehouse_id in self.warehouse_clients:
            await self._safe_broadcast(self.warehouse_clients[warehouse_id], json.dumps(message))

    async def broadcast_to_all(self, message: dict):
        """ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð²ÑÐµÐ¼ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð½Ñ‹Ð¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼"""
        all_clients = set()
        all_clients.update(self.admin_clients)
        all_clients.update(self.operator_clients)
        for clients in self.warehouse_clients.values():
            all_clients.update(clients)

        await self._safe_broadcast(all_clients, json.dumps(message))

# ============================================
# WOOCOMMERCE Ð˜ÐÐ¢Ð•Ð“Ð ÐÐ¦Ð˜Ð¯
# ============================================
class WooCommerceIntegration:
    def __init__(self, config: dict):
        self.url = config['url']
        self.consumer_key = config['consumer_key']
        self.consumer_secret = config['consumer_secret']

    def fetch_new_orders(self):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð½Ð¾Ð²Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ð¸Ð· WooCommerce"""
        # Ð’Ñ€ÐµÐ¼ÐµÐ½Ð½Ð¾ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¾ - Ñ‚Ñ€ÐµÐ±ÑƒÐµÑ‚ÑÑ Ð¼Ð¾Ð´ÑƒÐ»ÑŒ requests
        logger.warning("WooCommerce integration disabled - install 'requests' module")
        return []
        # try:
        #     endpoint = f"{self.url}/wp-json/wc/v3/orders"
        #     params = {
        #         'status': 'processing',
        #         'per_page': 10
        #     }
        #
        #     response = requests.get(
        #         endpoint,
        #         params=params,
        #         auth=(self.consumer_key, self.consumer_secret),
        #         timeout=10
        #     )
        #
        #     if response.status_code == 200:
        #         return response.json()
        #     else:
        #         logger.error(f"WooCommerce API error: {response.status_code}")
        #         return []
        #
        # except Exception as e:
        #     logger.error(f"WooCommerce fetch error: {e}")
        #     return []

# ============================================
# ÐžÐ¡ÐÐžÐ’ÐÐžÐ™ Ð¡Ð•Ð Ð’Ð•Ð 
# ============================================
class UnifiedServer:
    def __init__(self):
        self.db = Database(DB_PATH)
        self._repair_legacy_article_numbers()
        self.sessions = SessionManager()
        self._api_scan_lock = None  # asyncio.Lock(), Ð¸Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€ÑƒÐµÑ‚ÑÑ Ð² start()
        self.woocommerce = WooCommerceIntegration(WOOCOMMERCE_CONFIG)
        # self.pdf_parser = LieferscheinPDFParser()
        # (Ð“Ð´Ðµ ÑÐ¾Ð·Ð´Ð°ÑŽÑ‚ÑÑ Ð´Ñ€ÑƒÐ³Ð¸Ðµ Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ñ‹)
        self.kunden_monitor = KundenCSVMonitor(KUNDEN_CSV_PATH, self.db)
        # self.auftrag_parser = AuftragPDFParser()  # DEPRECATED - replaced by CSV

        # # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ Ð¸Ð¼ÐµÐ½Ð° ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² Ð² ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ñ… Ð·Ð°ÐºÐ°Ð·Ð°Ñ… Ð¸Ð· kunden.csv
        # if self.auftrag_parser.kunden_dict:
        #     logger.info("Updating existing orders with kunde names from kunden.csv...")
        #     self.db.update_kunde_names_from_csv(self.auftrag_parser.kunden_dict)

        # Ð˜Ð¼Ð¿Ð¾Ñ€Ñ‚Ð¸Ñ€ÑƒÐµÐ¼ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð° Ð»Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÐ¸ Ð¸Ð· KUNDENLISTE (Ð¾Ð´Ð¸Ð½ Ñ€Ð°Ð· Ð¿Ñ€Ð¸ Ð¿ÐµÑ€Ð²Ð¾Ð¼ Ð·Ð°Ð¿ÑƒÑÐºÐµ)
        kundenliste_csv_path = Path(__file__).parent / 'KUNDENLISTE  Ð´Ð»Ñ Ñ‚ÐµÑÑ‚Ð°.csv'
        self.db.import_logistics_from_csv(kundenliste_csv_path)

        # NEW: Initialize Stock Manager for smart production planning with DB persistence
        self.stock_manager = VirtualStockManager(database=self.db)
        logger.info("âœ“ ÐœÐµÐ½ÐµÐ´Ð¶ÐµÑ€ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¾Ð² Ð¸Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€Ð¾Ð²Ð°Ð½ (Ð‘Ð”)")

        # NEW: Initialize Resource Manager for production capacity planning
        self.resource_manager = ResourceManager(db_path=str(DB_PATH))
        logger.info("âœ“ ResourceManager Ð¸Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€Ð¾Ð²Ð°Ð½")

        # NEW: Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€ÑƒÐµÐ¼ LogisticsManager Ñ ResourceManager Ð´Ð»Ñ Ð¿Ñ€Ð¾Ð²ÐµÑ€ÐºÐ¸ Ð¼Ð¾Ñ‰Ð½Ð¾ÑÑ‚Ð¸
        self.logistics_manager = LogisticsManager(self.db, self.resource_manager)
        logger.info("âœ“ LogisticsManager Ð¸Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€Ð¾Ð²Ð°Ð½ Ñ ResourceManager")

        # NEW: Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€ÑƒÐµÐ¼ ProductionPlanner Ð´Ð»Ñ ÑƒÐ¼Ð½Ð¾Ð³Ð¾ Ð¿Ð»Ð°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ
        self.production_planner = ProductionPlanner(self.db, self.resource_manager, VirtualStockManager(database=self.db))
        logger.info("âœ“ ProductionPlanner Ð¸Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€Ð¾Ð²Ð°Ð½")

        # NEW: Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€ÑƒÐµÐ¼ Zutaten V2 API Ð´Ð»Ñ ÑƒÐ¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ñ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð°Ð¼Ð¸ (LMIV)
        self.zutaten_api = ZutatenAPIHandlers(str(DB_PATH))
        self.zutaten_handlers = get_zutaten_message_handlers(self.zutaten_api)
        logger.info("âœ“ Zutaten V2 API Ð¸Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€Ð¾Ð²Ð°Ð½ (LMIV DE/NL/FR)")

        # NEW: Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€ÑƒÐµÐ¼ CSV Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€ Ð´Ð»Ñ Ð¸Ð¼Ð¿Ð¾Ñ€Ñ‚Ð° Ð·Ð°ÐºÐ°Ð·Ð¾Ð² Ð¸Ð· WISO ERP
        self.csv_monitor = WisoCSVMonitor(
            WISO_CSV_PATH,
            self.db,
            self.logistics_manager,
            self.on_new_csv_order,
            self.sessions  # Ð”Ð»Ñ broadcast ÑƒÐ²ÐµÐ´Ð¾Ð¼Ð»ÐµÐ½Ð¸Ð¹ Ð¾Ð± Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸ÑÑ…
        )

        # NEW: Monolith API Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€ Ð·Ð°ÐºÐ°Ð·Ð¾Ð² (ÐºÐ°Ð¶Ð´Ñ‹Ðµ 10 Ð¼Ð¸Ð½ÑƒÑ‚)
        self.api_monitor = ApiOrderMonitor(
            self.db,
            self.logistics_manager,
            self.on_new_api_order,
            self.sessions
        )
        logger.info("âœ“ Monolith API Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€ Ð¸Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€Ð¾Ð²Ð°Ð½")

        # # DEPRECATED: Ð¡Ñ‚Ð°Ñ€Ñ‹Ð¹ Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€ PDF Ñ„Ð°Ð¹Ð»Ð¾Ð² AuftragsbestÃ¤tigung
        # self.auftrag_monitor = AuftragMonitor(
        #     AUFTRAG_FOLDER,
        #     self.on_new_auftrag
        # )
        # Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€ÑƒÐµÐ¼ Rechnung Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€ (Ñ Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð¾Ð¼ Ðº Ð±Ð°Ð·Ðµ Ð´Ð°Ð½Ð½Ñ‹Ñ… Ð´Ð»Ñ fallback Ð¿Ð¾ Kunden-Nr)
        ftp_config = FTP_CONFIG if FTP_CONFIG.get('enabled') else None
        self.rechnung_monitor = RechnungMonitor(
            RECHNUNG_FOLDER,
            RECHNUNG_OUTPUT_FOLDER,
            ftp_config,
            db=self.db,
            sessions=self.sessions
        )

        # Backup scheduler state
        self._backup_last_run_keys = {
            'system': None,
            'documents': None
        }
        self._last_audit_cleanup_at = None
        self._ensure_user_action_audit_table()
        self._cleanup_old_user_action_logs()

    def _ensure_user_action_audit_table(self):
        """Create audit table for user actions if it does not exist."""
        try:
            with sqlite3.connect(AUDIT_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_action_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_time TEXT NOT NULL,
                        event_date TEXT NOT NULL,
                        user_id INTEGER,
                        username TEXT NOT NULL,
                        role TEXT,
                        action_type TEXT NOT NULL,
                        details TEXT,
                        client_ip TEXT
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_user_action_logs_date ON user_action_logs(event_date)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_user_action_logs_user ON user_action_logs(username)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_user_action_logs_time ON user_action_logs(event_time)"
                )
                conn.commit()
        except Exception as e:
            logger.error(f"[AUDIT] Failed to ensure audit table: {e}")

    def _cleanup_old_user_action_logs(self):
        """Keep only last 30 days of user action logs."""
        try:
            with sqlite3.connect(AUDIT_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM user_action_logs
                    WHERE event_date < date('now', 'localtime', '-30 day')
                    """
                )
                removed = cursor.rowcount or 0
                conn.commit()
                return int(removed)
        except Exception as e:
            logger.error(f"[AUDIT] Cleanup failed: {e}")
            return 0

    def _sanitize_audit_details(self, payload: dict) -> str:
        """Compact and safe payload preview for action audit."""
        try:
            data = dict(payload or {})
            data.pop('type', None)
            for key in (
                'password', 'past_date_password', 'smtp_password', 'token', 'access_token',
                'file_data', 'pdf_b64', 'content', 'attachment', 'binary'
            ):
                if key in data:
                    data[key] = '***'

            raw = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
            if len(raw) > 900:
                raw = raw[:900] + "...(truncated)"
            return raw
        except Exception:
            return "{}"

    def _log_user_action_sync(self, session, action_type: str, details: str, client_ip: str):
        """Sync insert into user action audit table."""
        try:
            now_iso = datetime.now().isoformat()
            event_date = now_iso[:10]
            with sqlite3.connect(AUDIT_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO user_action_logs (
                        event_time, event_date, user_id, username, role, action_type, details, client_ip
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso,
                        event_date,
                        int(getattr(session, 'user_id', 0) or 0),
                        str(getattr(session, 'username', '') or ''),
                        str(getattr(session, 'role', '') or ''),
                        str(action_type or ''),
                        str(details or ''),
                        str(client_ip or '')
                    )
                )
                conn.commit()
        except Exception as e:
            logger.error(f"[AUDIT] Insert failed: {e}")

    async def _audit_user_action(self, session, websocket, msg_type: str, payload: dict):
        """Async wrapper to persist user action logs."""
        skip_types = {
            'ping',
            'get_daily_stock_report',
            'get_inventory_articles',
            'get_server_status',
            'get_backup_history',
            'get_backup_settings',
            'get_comm_bootstrap',
            'get_user_activity_logs'
        }
        if not msg_type or msg_type in skip_types:
            return
        details = self._sanitize_audit_details(payload)
        client_ip = ""
        try:
            peer = websocket.remote_address
            if isinstance(peer, tuple) and peer:
                client_ip = str(peer[0])
            elif peer:
                client_ip = str(peer)
        except Exception:
            client_ip = ""
        await self._run_sync(self._log_user_action_sync, session, msg_type, details, client_ip)

    def _get_user_activity_logs_sync(self, date_str: str, username: Optional[str] = None, limit: int = 2000):
        """Sync query for user activity logs."""
        try:
            lim = max(1, min(int(limit or 500), 5000))
        except Exception:
            lim = 2000
        with sqlite3.connect(AUDIT_DB_PATH) as conn:
            cursor = conn.cursor()
            params = [date_str]
            sql = """
                SELECT event_time, username, role, action_type, details, client_ip
                FROM user_action_logs
                WHERE event_date = ?
            """
            if username:
                sql += " AND username = ?"
                params.append(username)
            sql += " ORDER BY event_time DESC LIMIT ?"
            params.append(lim)
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT username, COUNT(*) AS cnt
                FROM user_action_logs
                WHERE event_date = ?
                GROUP BY username
                ORDER BY cnt DESC, username ASC
                """,
                (date_str,)
            )
            users = [{'username': r[0], 'count': int(r[1] or 0)} for r in cursor.fetchall()]

        logs = []
        for r in rows:
            logs.append({
                'event_time': r[0],
                'username': r[1],
                'role': r[2],
                'action_type': r[3],
                'details': r[4],
                'client_ip': r[5]
            })
        return {'logs': logs, 'users': users}

    async def handle_get_user_activity_logs(self, websocket, data, session):
        """Return user action logs for selected day (admin-only, password-protected)."""
        if session.role != 'admin':
            await websocket.send(json.dumps({'type': 'user_activity_logs_data', 'success': False, 'message': 'Forbidden'}))
            return

        password = str(data.get('admin_password', '') or '')
        if password != ADMIN_AUDIT_PASSWORD:
            await websocket.send(json.dumps({'type': 'user_activity_logs_data', 'success': False, 'message': 'Неверный пароль'}))
            return

        date_str = str(data.get('date') or datetime.now().strftime('%Y-%m-%d'))
        username = str(data.get('username') or '').strip() or None
        limit = data.get('limit', 2000)
        result = await self._run_sync(self._get_user_activity_logs_sync, date_str, username, limit)
        await websocket.send(json.dumps({
            'type': 'user_activity_logs_data',
            'success': True,
            'date': date_str,
            'username': username or '',
            'logs': result.get('logs', []),
            'users': result.get('users', [])
        }))

    def _get_client_order_history_sync(self, days: int = 30, query: str = '') -> dict:
        """Build client-centric order history from action audit for the selected period."""
        try:
            period_days = max(1, min(int(days or 30), 60))
        except Exception:
            period_days = 30

        query_norm = str(query or '').strip().lower()
        cutoff_iso = (datetime.now() - timedelta(days=period_days)).isoformat()
        relevant_types = (
            'start_viewing_order',
            'order_printed',
            'labels_printed',
            'boxes_info',
            'boxes_info_saved',
            'get_customer_shipping_doc',
            'ui_interaction'
        )

        events_by_order = defaultdict(list)
        order_ids = set()

        with sqlite3.connect(AUDIT_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT event_time, username, role, action_type, details, client_ip
                FROM user_action_logs
                WHERE event_time >= ?
                  AND action_type IN ({})
                ORDER BY event_time ASC
                """.format(",".join("?" for _ in relevant_types)),
                (cutoff_iso, *relevant_types)
            )
            rows = cursor.fetchall()

        for row in rows:
            raw_details = str(row['details'] or '').strip()
            details_obj = {}
            if raw_details:
                try:
                    details_obj = json.loads(raw_details)
                except Exception:
                    details_obj = {}

            order_id = str(details_obj.get('order_id') or '').strip()
            if not order_id and isinstance(details_obj.get('payload'), dict):
                order_id = str(details_obj.get('payload', {}).get('order_id') or '').strip()
            if not order_id:
                continue

            order_ids.add(order_id)
            events_by_order[order_id].append({
                'event_time': str(row['event_time'] or ''),
                'username': str(row['username'] or ''),
                'role': str(row['role'] or ''),
                'action_type': str(row['action_type'] or ''),
                'client_ip': str(row['client_ip'] or ''),
                'details': details_obj
            })

        # Pull client/order metadata for all involved orders.
        order_meta = {}
        if order_ids:
            with self.db.get_connection() as db_conn:
                db_conn.row_factory = sqlite3.Row
                cur = db_conn.cursor()
                ids = sorted(order_ids)
                chunk_size = 900
                for i in range(0, len(ids), chunk_size):
                    chunk = ids[i:i + chunk_size]
                    cur.execute(
                        """
                        SELECT order_id, order_data
                        FROM orders
                        WHERE order_id IN ({})
                        """.format(",".join("?" for _ in chunk)),
                        chunk
                    )
                    for rec in cur.fetchall():
                        od_raw = str(rec['order_data'] or '')
                        od = {}
                        if od_raw:
                            try:
                                od = json.loads(od_raw)
                            except Exception:
                                od = {}
                        order_meta[str(rec['order_id'])] = {
                            'kunde': str(od.get('kunde') or '').strip(),
                            'kunden_nr': str(od.get('kunden_nr') or '').strip(),
                            'auftrag_nr': str(od.get('auftrag_nr') or '').strip(),
                            'address': str(od.get('address') or '').strip(),
                        }

        clients = defaultdict(list)
        total_events = 0
        total_orders = 0

        for order_id, events in events_by_order.items():
            if not events:
                continue

            meta = order_meta.get(order_id, {})
            kunde = meta.get('kunde', '')
            kunden_nr = meta.get('kunden_nr', '')
            auftrag_nr = meta.get('auftrag_nr', '')

            # Enrich client data from event payload if DB metadata is missing.
            for ev in events:
                d = ev.get('details') or {}
                if not kunde:
                    kunde = str(d.get('kunde') or '').strip() or kunde
                if not kunden_nr:
                    kunden_nr = str(d.get('kunden_nr') or '').strip() or kunden_nr
                if not auftrag_nr:
                    auftrag_nr = str(d.get('lieferschein') or '').strip() or auftrag_nr

            if not kunde:
                kunde = "Unknown client"
            if not auftrag_nr:
                auftrag_nr = order_id

            first_event_time = events[0]['event_time']
            last_event_time = events[-1]['event_time']

            opened_times = [ev['event_time'] for ev in events if ev['action_type'] == 'start_viewing_order']
            printed_events = [ev for ev in events if ev['action_type'] in ('order_printed', 'labels_printed')]
            boxes_events = [ev for ev in events if ev['action_type'] == 'boxes_info']

            label_types = []
            seen_labels = set()
            for ev in printed_events:
                det = ev.get('details') or {}
                lang = str(det.get('label_language') or det.get('language') or '').strip()
                if lang and lang not in seen_labels:
                    seen_labels.add(lang)
                    label_types.append(lang)

            printed_by = sorted({str(ev.get('username') or '') for ev in printed_events if str(ev.get('username') or '')})

            box_history = []
            for ev in boxes_events:
                det = ev.get('details') or {}
                try:
                    bc = int(float(det.get('boxes_count') or 0))
                except Exception:
                    bc = 0
                box_history.append({
                    'time': ev.get('event_time', ''),
                    'boxes_count': bc,
                    'username': ev.get('username', '')
                })

            last_boxes_count = box_history[-1]['boxes_count'] if box_history else 0
            closed_at = box_history[-1]['time'] if box_history else ''

            # Timeline for diagnostics.
            timeline = []
            for ev in events:
                det = ev.get('details') or {}
                timeline_item = {
                    'time': ev.get('event_time', ''),
                    'action': ev.get('action_type', ''),
                    'user': ev.get('username', ''),
                    'role': ev.get('role', ''),
                    'ip': ev.get('client_ip', ''),
                }
                if 'boxes_count' in det:
                    try:
                        timeline_item['boxes_count'] = int(float(det.get('boxes_count') or 0))
                    except Exception:
                        timeline_item['boxes_count'] = 0
                lang = str(det.get('label_language') or det.get('language') or '').strip()
                if lang:
                    timeline_item['label_type'] = lang
                # Детали UI-аудита для полной трассировки действий.
                payload_obj = det.get('payload', {}) if isinstance(det.get('payload', {}), dict) else {}
                event_name = str(det.get('event_name') or '').strip()
                if event_name:
                    timeline_item['event_name'] = event_name
                widget_text = str(payload_obj.get('widget_text') or '').strip()
                if widget_text:
                    timeline_item['widget_text'] = widget_text
                selected_values = str(payload_obj.get('selected_values') or '').strip()
                if selected_values:
                    timeline_item['selected_values'] = selected_values
                keysym = str(payload_obj.get('keysym') or '').strip()
                if keysym:
                    timeline_item['keysym'] = keysym
                timeline.append(timeline_item)

            # Client filter
            if query_norm:
                haystack = " ".join([
                    order_id.lower(),
                    str(auftrag_nr).lower(),
                    str(kunde).lower(),
                    str(kunden_nr).lower(),
                    " ".join(label_types).lower()
                ])
                if query_norm not in haystack:
                    continue

            client_id = kunden_nr or "-"
            client_key = f"{client_id}|{kunde.strip().lower()}"

            clients[client_key].append({
                'order_id': order_id,
                'auftrag_nr': auftrag_nr,
                'kunde': kunde,
                'kunden_nr': kunden_nr,
                'opened_at': opened_times[0] if opened_times else '',
                'first_event_at': first_event_time,
                'last_event_at': last_event_time,
                'closed_at': closed_at,
                'print_count': len(printed_events),
                'printed_twice_or_more': len(printed_events) > 1,
                'label_types': label_types,
                'printed_by': printed_by,
                'boxes_last_count': last_boxes_count,
                'boxes_history': box_history,
                'events_count': len(events),
                'timeline': timeline,
            })

            total_events += len(events)
            total_orders += 1

        client_items = []
        for client_key, orders in clients.items():
            cid, cname = client_key.split('|', 1)
            orders_sorted = sorted(orders, key=lambda x: x.get('last_event_at', ''), reverse=True)
            for idx, order_item in enumerate(orders_sorted, start=1):
                order_item['order_no'] = idx
            client_items.append({
                'client_id': cid,
                'client_name': orders_sorted[0].get('kunde', cname),
                'orders_count': len(orders_sorted),
                'orders': orders_sorted
            })

        client_items.sort(key=lambda c: (str(c.get('client_name') or '').lower(), str(c.get('client_id') or '').lower()))

        return {
            'days': period_days,
            'query': query_norm,
            'clients': client_items,
            'stats': {
                'clients_count': len(client_items),
                'orders_count': total_orders,
                'events_count': total_events
            }
        }

    async def handle_get_client_order_history(self, websocket, data, session):
        """Return client order history based on action audit (admin-only)."""
        if session.role != 'admin':
            await self.safe_send(websocket, {
                'type': 'client_order_history_data',
                'success': False,
                'message': 'Forbidden'
            })
            return

        days = data.get('days', 30)
        query = str(data.get('query') or '')
        result = await self._run_sync(self._get_client_order_history_sync, days, query)
        await self.safe_send(websocket, {
            'type': 'client_order_history_data',
            'success': True,
            'days': result.get('days', 30),
            'query': result.get('query', ''),
            'clients': result.get('clients', []),
            'stats': result.get('stats', {})
        })

    def _repair_legacy_article_numbers(self):
        """
        Ð›ÐµÑ‡Ð¸Ñ‚ ÑÑ‚Ð°Ñ€Ñ‹Ðµ Ð´ÑƒÐ±Ð»Ð¸ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Ð±ÐµÐ· Ð²ÐµÐ´ÑƒÑ‰Ð¸Ñ… Ð½ÑƒÐ»ÐµÐ¹ (Ð¿Ñ€Ð¸Ð¼ÐµÑ€: 5130 Ð¸ 05130).
        ÐŸÑ€Ð°Ð²Ð¸Ð»Ð¾: ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ Ð¾Ð±Ð°, ÑÐ¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ ÐºÐ°Ð½Ð¾Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ð¹ (zfill(5)), legacy Ð²Ñ‹ÐºÐ»ÑŽÑ‡Ð°ÐµÐ¼.
        ÐžÑÑ‚Ð°Ñ‚ÐºÐ¸ legacy Ð¿ÐµÑ€ÐµÐ½Ð¾ÑÐ¸Ð¼ Ð² ÐºÐ°Ð½Ð¾Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ».
        """
        try:
            with self.db.safe_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT article_nr FROM recipes")
                all_articles = [str(r[0]).strip() for r in cursor.fetchall() if r and r[0] is not None]

                pairs = []
                all_set = set(all_articles)
                for art in all_articles:
                    if art.isdigit() and len(art) < 5:
                        canon = art.zfill(5)
                        if canon in all_set and art != canon:
                            pairs.append((art, canon))

                fixed = 0
                for legacy, canon in sorted(set(pairs)):
                    # 1) ÐŸÐµÑ€ÐµÐ½Ð¾ÑÐ¸Ð¼ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸ legacy -> canon Ð¿Ð¾ Ð´Ð°Ñ‚Ð°Ð¼ (ÑÑƒÐ¼Ð¼Ð°)
                    cursor.execute(
                        "SELECT date, quantity, COALESCE(last_editor,'System') FROM daily_stock_reports WHERE article_nr=?",
                        (legacy,)
                    )
                    for date_str, qty, editor in cursor.fetchall():
                        cursor.execute(
                            "SELECT quantity FROM daily_stock_reports WHERE date=? AND article_nr=?",
                            (date_str, canon)
                        )
                        row = cursor.fetchone()
                        if row:
                            new_qty = float(row[0] or 0) + float(qty or 0)
                            cursor.execute(
                                "UPDATE daily_stock_reports SET quantity=?, updated_at=? WHERE date=? AND article_nr=?",
                                (new_qty, datetime.now().isoformat(), date_str, canon)
                            )
                        else:
                            cursor.execute(
                                """
                                INSERT INTO daily_stock_reports (date, article_nr, quantity, last_editor, created_at, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?)
                                """,
                                (date_str, canon, float(qty or 0), editor, datetime.now().isoformat(), datetime.now().isoformat())
                            )
                    cursor.execute("DELETE FROM daily_stock_reports WHERE article_nr=?", (legacy,))

                    # 2) Legacy Ñ€ÐµÑ†ÐµÐ¿Ñ‚ Ð²Ñ‹ÐºÐ»ÑŽÑ‡Ð°ÐµÐ¼ (ÐºÐ°Ð½Ð¾Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ð¹ Ð¾ÑÑ‚Ð°Ð²Ð»ÑÐµÐ¼ Ð°ÐºÑ‚Ð¸Ð²Ð½Ñ‹Ð¼)
                    cursor.execute(
                        "UPDATE recipes SET active=0, updated_at=? WHERE article_nr=?",
                        (datetime.now().isoformat(), legacy)
                    )
                    fixed += 1

                if fixed:
                    logger.info(f"[REPAIR] Legacy article duplicates fixed: {fixed}")
                conn.commit()
        except Exception as e:
            logger.error(f"[REPAIR] Failed to repair legacy article numbers: {e}")

    def _resolve_recipe_article_nr_for_write(self, cursor, raw_article_nr):
        """
        Ð’Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ article_nr Ð´Ð»Ñ UPDATE/INSERT Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°.
        ÐŸÑ€Ð¸Ð¾Ñ€Ð¸Ñ‚ÐµÑ‚: Ñ‚Ð¾Ñ‡Ð½Ð¾Ðµ ÑÐ¾Ð²Ð¿Ð°Ð´ÐµÐ½Ð¸Ðµ -> zfill(5) -> Ð¸ÑÑ…Ð¾Ð´Ð½Ð¾Ðµ Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ.
        Ð­Ñ‚Ð¾ Ð·Ð°Ñ‰Ð¸Ñ‰Ð°ÐµÑ‚ Ð¾Ñ‚ ÑÐ¸Ñ‚ÑƒÐ°Ñ†Ð¸Ð¸, ÐºÐ¾Ð³Ð´Ð° Ñ€ÐµÐ´Ð°ÐºÑ‚Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ 5130 ÑÐ»ÑƒÑ‡Ð°Ð¹Ð½Ð¾ Ð¾Ð±Ð½Ð¾Ð²Ð»ÑÐµÑ‚ 05130.
        """
        article_nr = str(raw_article_nr or "").strip()
        if not article_nr:
            return article_nr

        cursor.execute("SELECT 1 FROM recipes WHERE article_nr = ?", (article_nr,))
        if cursor.fetchone():
            return article_nr

        if article_nr.isdigit():
            padded = article_nr.zfill(5)
            cursor.execute("SELECT 1 FROM recipes WHERE article_nr = ?", (padded,))
            if cursor.fetchone():
                return padded

        return article_nr

    async def _run_sync(self, func, *args):
        """Ð—Ð°Ð¿ÑƒÑÐº ÑÐ¸Ð½Ñ…Ñ€Ð¾Ð½Ð½Ð¾Ð¹ Ñ„ÑƒÐ½ÐºÑ†Ð¸Ð¸ Ð² Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ (Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð½Ðµ Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ ÑÐµÑ€Ð²ÐµÑ€)"""
        loop = asyncio.get_running_loop()
        # Prefer dedicated executor created in start() for monitor+DB workload.
        executor = getattr(self, '_monitor_executor', None)
        return await loop.run_in_executor(executor, func, *args)

    async def safe_send(self, websocket, message: dict) -> bool:
        """Ð‘ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð°Ñ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÐºÐ° ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ - Ð½Ðµ Ð¿Ð°Ð´Ð°ÐµÑ‚ ÐµÑÐ»Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡Ð¸Ð»ÑÑ"""
        try:
            await websocket.send(json.dumps(message))
            return True
        except Exception as e:
            # ÐšÐ»Ð¸ÐµÐ½Ñ‚ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡Ð¸Ð»ÑÑ - ÑÑ‚Ð¾ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ð¾, Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð»Ð¾Ð³Ð¸Ñ€ÑƒÐµÐ¼
            logger.debug(f"ÐÐµ ÑƒÐ´Ð°Ð»Ð¾ÑÑŒ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ñƒ: {e}")
            return False

    async def handle_client(self, websocket):
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ñ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð° (Ð˜ÑÐ¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¾ ÑƒÐ´Ð°Ð»ÐµÐ½Ð¸Ðµ ÑÐµÑÑÐ¸Ð¹)"""
        is_authorized = False # Ð¤Ð»Ð°Ð³: Ð±Ñ‹Ð»Ð° Ð»Ð¸ ÑƒÑÐ¿ÐµÑˆÐ½Ð°Ñ Ð°Ð²Ñ‚Ð¾Ñ€Ð¸Ð·Ð°Ñ†Ð¸Ñ
        
        try:
            # ÐŸÐµÑ€Ð²Ð¾Ðµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð´Ð¾Ð»Ð¶Ð½Ð¾ Ð±Ñ‹Ñ‚ÑŒ Ð°Ð²Ñ‚Ð¾Ñ€Ð¸Ð·Ð°Ñ†Ð¸ÐµÐ¹
            # logger.info("[AUTH] Waiting for auth message...")
            auth_message = await websocket.recv()
            auth_data = json.loads(auth_message)

            if auth_data.get('type') != 'auth':
                await websocket.send(json.dumps({'type': 'auth_error', 'message': 'Auth required'}))
                return

            username = auth_data.get('username')
            password = auth_data.get('password')

            # ÐÑƒÑ‚ÐµÐ½Ñ‚Ð¸Ñ„Ð¸ÐºÐ°Ñ†Ð¸Ñ (Ð² executor Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð½Ðµ Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ event loop)
            user = await self._run_sync(self.db.authenticate_user, username, password)

            if not user:
                await websocket.send(json.dumps({'type': 'auth_error', 'message': 'Invalid credentials'}))
                return

            # Ð¡Ð¾Ð·Ð´Ð°Ñ‘Ð¼ ÑÐµÑÑÐ¸ÑŽ
            session_id = self.sessions.create_session(user, websocket)
            is_authorized = True # <--- ÐŸÐ¾Ð¼ÐµÑ‡Ð°ÐµÐ¼, Ñ‡Ñ‚Ð¾ ÑÐµÑÑÐ¸Ñ ÑÐ¾Ð·Ð´Ð°Ð½Ð°

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ð¿Ð¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð¸Ðµ
            await websocket.send(json.dumps({
                'type': 'auth_success',
                'session_id': session_id,
                'user': {
                    'user_id': user.user_id,
                    'username': user.username,
                    'first_name': getattr(user, 'first_name', ''),
                    'last_name': getattr(user, 'last_name', ''),
                    'display_name': getattr(user, 'display_name', user.username),
                    'role': user.role,
                    'warehouse_id': user.warehouse_id,
                    'permissions': user.permissions
                }
            }))

            logger.info(f"ÐšÐ»Ð¸ÐµÐ½Ñ‚ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½: {username} ({user.role})")

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ð½Ð°Ñ‡Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ
            await self.send_initial_data(websocket, user)

            # ÐžÐ±Ñ€Ð°Ð±Ð°Ñ‚Ñ‹Ð²Ð°ÐµÐ¼ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ
            async for message in websocket:
                await self.handle_message(websocket, message)

        except websockets.exceptions.ConnectionClosed:
            pass # Ð­Ñ‚Ð¾ Ð½Ð¾Ñ€Ð¼Ð°Ð»ÑŒÐ½Ð¾Ðµ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ, Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð²Ñ‹Ñ…Ð¾Ð´Ð¸Ð¼
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð² ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ð¸: {e}")
        finally:
            # Ð“ÐÐ ÐÐÐ¢Ð˜Ð ÐžÐ’ÐÐÐÐÐ¯ ÐžÐ§Ð˜Ð¡Ð¢ÐšÐ
            if is_authorized:
                self.sessions.remove_session(websocket)
                # logger.info("Ð¡ÐµÑÑÐ¸Ñ Ð¾Ñ‡Ð¸Ñ‰ÐµÐ½Ð° ÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ð¾")

    async def handle_import_history_files(self, websocket, data):
        """Ð¡ÐºÐ°Ð½Ð¸Ñ€ÑƒÐµÑ‚ Ð¿Ð°Ð¿ÐºÑƒ Ñ Ð³Ð¾Ð´Ð¾Ð²Ñ‹Ð¼Ð¸ Ð¾Ñ‚Ñ‡ÐµÑ‚Ð°Ð¼Ð¸ Ð¸ Ð·Ð°Ð½Ð¾ÑÐ¸Ñ‚ Ð² Ð‘Ð”"""
        history_folder = Path(r"\\server01\DATA\WISO_GOLABEL\history_sales")
        files = list(history_folder.glob("*.csv"))
        
        for file_path in files:
            logger.info(f"ÐŸÐ°Ñ€ÑÐ¸Ð½Ð³ Ñ„Ð°Ð¹Ð»Ð° Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ð¸: {file_path.name}")
            # Ð—Ð´ÐµÑÑŒ Ð±ÑƒÐ´ÐµÑ‚ Ð²Ð°Ñˆ ÐºÐ¾Ð´ Ð¾Ñ‚ÐºÑ€Ñ‹Ñ‚Ð¸Ñ CSV Ð¸ Ñ„Ð¾Ñ€Ð¼Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ ÑÐ¿Ð¸ÑÐºÐ° [ (Ð°Ñ€Ñ‚, Ð´Ð°Ñ‚Ð°, ÐºÐ¾Ð»Ð²Ð¾), ... ]
            # data_for_db = parse_csv(file_path) 
            # self.db.import_sales_history_bulk(data_for_db)
            
        await websocket.send(json.dumps({'type': 'success', 'message': f'Ð—Ð°Ð³Ñ€ÑƒÐ¶ÐµÐ½Ð¾ Ñ„Ð°Ð¹Ð»Ð¾Ð²: {len(files)}'}))          

    async def handle_get_production_breakdown(self, websocket, data):
        """Ð Ð°ÑÑ‡ÐµÑ‚ Ð¿Ð»Ð°Ð½Ð° Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð° (ÐÐ¡Ð˜ÐÐ¥Ð ÐžÐÐÐÐ¯ Ð’Ð•Ð Ð¡Ð˜Ð¯ - ÐÐ• Ð’Ð•Ð¨ÐÐ•Ð¢ Ð¡Ð•Ð Ð’Ð•Ð )"""
        try:
            logger.info("Calculating production breakdown...")
            
            date_str = data.get('date')
            if not date_str:
                date_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

            # === Ð“Ð›ÐÐ’ÐÐžÐ• Ð˜Ð¡ÐŸÐ ÐÐ’Ð›Ð•ÐÐ˜Ð•: Ð—Ð°Ð³Ñ€ÑƒÐ·ÐºÐ° Ð´Ð°Ð½Ð½Ñ‹Ñ… Ð² Ð¿Ð¾Ñ‚Ð¾ÐºÐ°Ñ… ===
            # Ð•ÑÐ»Ð¸ Ð´Ð¸ÑÐº ÑÐ¿Ð¸Ñ‚, ÑÐµÑ€Ð²ÐµÑ€ Ð¿Ñ€Ð¾Ð´Ð¾Ð»Ð¶Ð¸Ñ‚ Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ñ‚ÑŒ Ð´Ð»Ñ Ð´Ñ€ÑƒÐ³Ð¸Ñ…, Ð¿Ð¾ÐºÐ° ÑÑ‚Ð¾Ñ‚ Ð¿Ð¾Ñ‚Ð¾Ðº Ð¶Ð´ÐµÑ‚
            
            # 1. Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ñ‹
            recipes = await self._run_sync(self.db.get_all_recipes)
            
            # 2. Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ð½Ð° Ð´Ð°Ñ‚Ñƒ
            orders = await self._run_sync(self.db.get_orders_by_production_date, date_str)
            
            # 3. Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¾Ð² (ÐµÑÐ»Ð¸ Ð½ÑƒÐ¶Ð½Ð¾ Ð´Ð»Ñ Ñ€Ð°ÑÑ‡ÐµÑ‚Ð°)
            stock_date = datetime.now().strftime('%Y-%m-%d')
            daily_stock = await self._run_sync(self.db.get_daily_stock_report, stock_date)
            
            # 4. Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ð·Ð°Ñ„Ð¸ÐºÑÐ¸Ñ€Ð¾Ð²Ð°Ð½Ð½Ñ‹Ð¹ Ð¿Ð»Ð°Ð½ (Locked Plan)
            locked_plan = await self._run_sync(self.db.get_locked_production_plan, date_str)
            
            # ÐŸÑ€ÐµÐ²Ñ€Ð°Ñ‰Ð°ÐµÐ¼ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸ Ð² ÑÐ»Ð¾Ð²Ð°Ñ€ÑŒ Ð´Ð»Ñ Ð±Ñ‹ÑÑ‚Ñ€Ð¾Ð³Ð¾ Ð¿Ð¾Ð¸ÑÐºÐ°
            stock_dict = {item['article_nr']: item['quantity'] for item in daily_stock}
            
            # === Ð Ð°ÑÑ‡ÐµÑ‚ Ð»Ð¾Ð³Ð¸ÐºÐ¸ (ÑÑ‚Ð¾ Ð±Ñ‹ÑÑ‚Ñ€Ð¾, Ð¼Ð¾Ð¶Ð½Ð¾ Ð¾ÑÑ‚Ð°Ð²Ð¸Ñ‚ÑŒ Ð·Ð´ÐµÑÑŒ) ===
            breakdown = {}
            
            # Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ñ
            for r in recipes:
                art = r['article_nr']
                breakdown[art] = {
                    'article_nr': art,
                    'name': r['name'],
                    'dough_id': r['dough_id'],
                    'items_per_tray': r['items_per_tray'] or 1.0,
                    'total_ordered': 0,
                    'stock': stock_dict.get(art, 0),
                    'locked_qty': locked_plan.get(art, 0) if locked_plan else 0,
                    'to_bake': 0
                }

            # Ð¡ÑƒÐ¼Ð¼Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
            for order in orders:
                try:
                    o_data = json.loads(order['order_data'])
                    for item in o_data.get('artikel', []):
                        nr = item.get('artikel_nr') or item.get('nummer')
                        qty = float(item.get('menge', 0) or 0)
                        if nr in breakdown:
                            breakdown[nr]['total_ordered'] += qty
                except:
                    continue

            # Ð¤Ð¸Ð½Ð°Ð»ÑŒÐ½Ñ‹Ð¹ Ð¿Ð¾Ð´ÑÑ‡ÐµÑ‚
            result_list = []
            for art, val in breakdown.items():
                needed = val['total_ordered'] - val['stock']
                if needed < 0: needed = 0
                
                # Ð•ÑÐ»Ð¸ Ð¿Ð»Ð°Ð½ Ð·Ð°Ñ„Ð¸ÐºÑÐ¸Ñ€Ð¾Ð²Ð°Ð½ Ð²Ñ€ÑƒÑ‡Ð½ÑƒÑŽ, Ð±ÐµÑ€ÐµÐ¼ ÐµÐ³Ð¾
                if val['locked_qty'] > 0:
                    needed = val['locked_qty']
                
                val['to_bake'] = needed
                
                # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ Ð°ÐºÑ‚Ð¸Ð²Ð½Ð¾ÑÑ‚ÑŒ
                if val['total_ordered'] > 0 or val['stock'] > 0 or val['locked_qty'] > 0:
                    result_list.append(val)

            await self.send_json(websocket, {
                'type': 'production_breakdown',
                'date': date_str,
                'data': result_list
            })
            logger.info(f"Production breakdown sent for {date_str}")

        except Exception as e:
            logger.error(f"Error in production breakdown: {e}", exc_info=True)
            await self.send_error(websocket, f"Calculation error: {e}")

    async def handle_update_client_logistics(self, websocket, data):
        # Ð’ÐÐ–ÐÐž: ÐŸÐµÑ€ÐµÐ´Ð°Ñ‘Ð¼ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð° Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð¾Ð², ÐµÑÐ»Ð¸ Ð¾Ð½Ð¸ ÐµÑÑ‚ÑŒ
        client_id = data['client_id']
        route_id = data['route_id']

        success = self.db.update_client_logistics(
            client_id,
            route_id,
            data['transport'],
            data['point'],
            rules=data.get('rules')  # <-- Ð”ÐžÐ‘ÐÐ’Ð›Ð•ÐÐž!
        )
        if success:
            logger.info(f"Client logistics updated: {client_id} with rules: {data.get('rules')}")

            # ÐÐžÐ’ÐžÐ•: ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ route_id Ð¸ route_name Ð²Ð¾ Ð²ÑÐµÑ… Ð·Ð°ÐºÐ°Ð·Ð°Ñ… ÑÑ‚Ð¾Ð³Ð¾ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°
            updated_order_ids = self.db.update_orders_route_by_client(client_id, route_id)

            # Broadcast Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ Ð·Ð°ÐºÐ°Ð·Ð¾Ð² Ð’Ð¡Ð•Ðœ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼
            if updated_order_ids:
                logger.info(f"Syncing route change to {len(updated_order_ids)} orders for client {client_id}")

                # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ route_name Ð´Ð»Ñ broadcast
                conn = self.db.get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT route_name FROM logistics_routes WHERE route_id = ?", (route_id,))
                row = cursor.fetchone()
                route_name = row['route_name'] if row else route_id
                conn.close()

                # Broadcast ÐºÐ°Ð¶Ð´Ð¾Ð³Ð¾ Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ð¾Ð³Ð¾ Ð·Ð°ÐºÐ°Ð·Ð°
                for order_id in updated_order_ids:
                    await self.sessions.broadcast_to_all({
                        'type': 'order_update',
                        'order_id': order_id,
                        'update': {
                            'route_id': route_id,
                            'route_name': route_name
                        }
                    })

            # Broadcast logistics data Ð²ÑÐµÐ¼ (Ð½Ðµ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ admin)
            all_logistics = self.db.get_all_logistics()
            await self.sessions.broadcast_to_all({
                'type': 'logistics_data',
                'routes': all_logistics['routes'],
                'clients': all_logistics['clients']
            })

    async def kunden_monitor_loop(self):
        """Ð¦Ð¸ÐºÐ» Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³Ð° ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²"""
        logger.info("Kunden monitor started")
        loop = asyncio.get_event_loop()
        consecutive_errors = 0
        while True:
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, self.kunden_monitor.scan),
                    timeout=30
                )
                consecutive_errors = 0
                await asyncio.sleep(10)
            except asyncio.TimeoutError:
                consecutive_errors += 1
                backoff = min(60, 10 * consecutive_errors)
                logger.warning(f"Kunden monitor scan timed out (errors: {consecutive_errors})")
                await asyncio.sleep(backoff)
            except Exception as e:
                consecutive_errors += 1
                backoff = min(60, 10 * consecutive_errors)
                logger.error(f"Kunden monitor error: {e}")
                await asyncio.sleep(backoff)

    async def handle_create_route(self, websocket, data):
        """Ð¡Ð¾Ð·Ð´Ð°Ñ‚ÑŒ Ð½Ð¾Ð²Ñ‹Ð¹ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚"""
        route_id = data['route_id']
        name = data['route_name']
        conn = self.db.get_connection()
        try:
            conn.execute("INSERT OR IGNORE INTO logistics_routes (route_id, route_name, delivery_days, lead_time, updated_at) VALUES (?, ?, '[]', 1, ?)", 
                         (route_id, name, datetime.now().isoformat()))
            conn.commit()
        except Exception as e:
            logger.error(f"Error creating route: {e}")
        finally:
            conn.close()

        await self.handle_get_all_logistics(websocket)
        # Broadcast Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð²ÑÐµÐ¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼
        await self.broadcast_logistics_update()

    async def handle_update_route_name(self, websocket, data):
        """ÐŸÐµÑ€ÐµÐ¸Ð¼ÐµÐ½Ð¾Ð²Ð°Ñ‚ÑŒ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚"""
        route_id = data['route_id']
        new_name = data['new_name']

        conn = self.db.get_connection()
        try:
            conn.execute("UPDATE logistics_routes SET route_name = ? WHERE route_id = ?", (new_name, route_id))
            conn.commit()
        except Exception as e:
            logger.error(f"Error updating route: {e}")
        finally:
            conn.close()

        # ÐÐžÐ’ÐžÐ•: ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ route_name Ð²Ð¾ Ð²ÑÐµÑ… Ð·Ð°ÐºÐ°Ð·Ð°Ñ… Ñ ÑÑ‚Ð¸Ð¼ route_id
        updated_order_ids = self.db.update_orders_route_name_by_route_id(route_id, new_name)

        # Broadcast Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
        if updated_order_ids:
            logger.info(f"Syncing route rename to {len(updated_order_ids)} orders for route {route_id}")
            for order_id in updated_order_ids:
                await self.sessions.broadcast_to_all({
                    'type': 'order_update',
                    'order_id': order_id,
                    'update': {
                        'route_name': new_name
                    }
                })

        await self.handle_get_all_logistics(websocket)
        # Broadcast Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð²ÑÐµÐ¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼
        await self.broadcast_logistics_update()

    async def handle_delete_route(self, websocket, data):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚"""
        route_id = data['route_id']

        # ÐÐžÐ’ÐžÐ•: Ð¡Ð½Ð°Ñ‡Ð°Ð»Ð° Ð¿ÐµÑ€ÐµÐ½Ð¾ÑÐ¸Ð¼ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ð½Ð° 'free' Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚
        updated_order_ids = self.db.update_orders_route_to_free(route_id)

        conn = self.db.get_connection()
        try:
            # Ð£Ð´Ð°Ð»ÑÐµÐ¼ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚
            conn.execute("DELETE FROM logistics_routes WHERE route_id = ?", (route_id,))
            # Ð¡Ð±Ñ€Ð°ÑÑ‹Ð²Ð°ÐµÐ¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² Ð½Ð° 'free'
            conn.execute("UPDATE client_routes SET route_id='free' WHERE route_id = ?", (route_id,))
            conn.commit()
        except Exception as e:
            logger.error(f"Error deleting route: {e}")
        finally:
            conn.close()

        # Broadcast Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
        if updated_order_ids:
            logger.info(f"Moving {len(updated_order_ids)} orders from deleted route {route_id} to 'free'")

            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ route_name Ð´Ð»Ñ 'free'
            with self.db.safe_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT route_name FROM logistics_routes WHERE route_id = 'free'")
                row = cursor.fetchone()
                free_route_name = row['route_name'] if row else 'Ð¡Ð²Ð¾Ð±Ð¾Ð´Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ñ‹'

            for order_id in updated_order_ids:
                await self.sessions.broadcast_to_all({
                    'type': 'order_update',
                    'order_id': order_id,
                    'update': {
                        'route_id': 'free',
                        'route_name': free_route_name
                    }
                })

        await self.handle_get_all_logistics(websocket)
        # Broadcast Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð²ÑÐµÐ¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼
        await self.broadcast_logistics_update()

    async def broadcast_logistics_update(self):
        """ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð»Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÐ¸ Ð²ÑÐµÐ¼ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð½Ñ‹Ð¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼"""
        try:
            logistics_data = self.db.get_all_logistics()
            message = {
                'type': 'logistics_data',
                'routes': logistics_data['routes'],
                'clients': logistics_data['clients']
            }
            await self.sessions.broadcast_to_all(message)
            logger.debug("Broadcast logistics update to all clients")
        except Exception as e:
            logger.error(f"Error broadcasting logistics update: {e}")

    async def handle_update_order_date(self, websocket, data):
        """Ð ÑƒÑ‡Ð½Ð¾Ðµ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ðµ Ð´Ð°Ñ‚Ñ‹ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸"""
        order_id = data.get('order_id')
        new_delivery_date = data.get('delivery_date')

        logger.info(f"ðŸ“… Ð˜Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ðµ Ð´Ð°Ñ‚Ñ‹ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸: order_id={order_id}, new_date={new_delivery_date}")

        # Ð’Ð°Ð»Ð¸Ð´Ð°Ñ†Ð¸Ñ Ð´Ð°Ð½Ð½Ñ‹Ñ…
        if not order_id:
            logger.error("ÐžÑˆÐ¸Ð±ÐºÐ°: order_id Ð½Ðµ ÑƒÐºÐ°Ð·Ð°Ð½")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': 'ÐÐµ ÑƒÐºÐ°Ð·Ð°Ð½ Ð½Ð¾Ð¼ÐµÑ€ Ð·Ð°ÐºÐ°Ð·Ð°'
            }))
            return

        if not new_delivery_date:
            logger.error("ÐžÑˆÐ¸Ð±ÐºÐ°: delivery_date Ð½Ðµ ÑƒÐºÐ°Ð·Ð°Ð½")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': 'ÐÐµ ÑƒÐºÐ°Ð·Ð°Ð½Ð° Ð½Ð¾Ð²Ð°Ñ Ð´Ð°Ñ‚Ð° Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸'
            }))
            return

        # Ð’Ð°Ð»Ð¸Ð´Ð°Ñ†Ð¸Ñ Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚Ð° Ð´Ð°Ñ‚Ñ‹
        try:
            datetime.strptime(new_delivery_date, "%Y-%m-%d")
        except ValueError:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ°: Ð½ÐµÐ¿Ñ€Ð°Ð²Ð¸Ð»ÑŒÐ½Ñ‹Ð¹ Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚ Ð´Ð°Ñ‚Ñ‹: {new_delivery_date}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'ÐÐµÐ¿Ñ€Ð°Ð²Ð¸Ð»ÑŒÐ½Ñ‹Ð¹ Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚ Ð´Ð°Ñ‚Ñ‹: {new_delivery_date}. ÐžÐ¶Ð¸Ð´Ð°ÐµÑ‚ÑÑ YYYY-MM-DD'
            }))
            return

        try:
            # 1. ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ð°
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT order_data FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()

            if not row:
                logger.error(f"Order not found: {order_id}")
                await websocket.send(json.dumps({
                    'type': 'error',
                    'message': f'Ð—Ð°ÐºÐ°Ð· {order_id} Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½'
                }))
                return

            order_data = json.loads(row[0])
            kunden_nr = order_data.get('kunden_nr')

            # 2. Ð Ð°ÑÑÑ‡Ð¸Ñ‚Ð°Ñ‚ÑŒ Ð½Ð¾Ð²ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð° Ñ‡ÐµÑ€ÐµÐ· LogisticsManager
            order_date = order_data.get('date', datetime.now().strftime("%Y-%m-%d"))
            logistics_info = self.logistics_manager.calculate_dates(order_date, kunden_nr)

            # ÐŸÐµÑ€ÐµÐ¾Ð¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ Ð´Ð°Ñ‚Ñƒ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ (Ñ€ÑƒÑ‡Ð½Ð°Ñ ÑƒÑÑ‚Ð°Ð½Ð¾Ð²ÐºÐ°)
            logistics_info['delivery_date'] = new_delivery_date

            # ÐŸÐµÑ€ÐµÑÑ‡Ð¸Ñ‚Ñ‹Ð²Ð°ÐµÐ¼ Ð´Ð°Ñ‚Ñƒ Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð° Ð½Ð° Ð¾ÑÐ½Ð¾Ð²Ðµ Ð½Ð¾Ð²Ð¾Ð¹ Ð´Ð°Ñ‚Ñ‹ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸
            try:
                del_dt = datetime.strptime(new_delivery_date, "%Y-%m-%d")
                # Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð° Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð° Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ (-1 Ð´ÐµÐ½ÑŒ)
                prod_dt = del_dt - timedelta(days=1)
                # Ð•ÑÐ»Ð¸ Ð’Ð¾ÑÐºÑ€ÐµÑÐµÐ½ÑŒÐµ -> Ð¡ÑƒÐ±Ð±Ð¾Ñ‚Ð°
                if prod_dt.weekday() == 6:
                    prod_dt -= timedelta(days=1)
                logistics_info['production_date'] = prod_dt.strftime("%Y-%m-%d")
            except:
                logistics_info['production_date'] = new_delivery_date

            # 3. ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ Ð² Ð‘Ð”
            updates = {
                'delivery_date': logistics_info['delivery_date'],
                'production_date': logistics_info['production_date'],
                'route_id': logistics_info.get('route_id'),
                'route_name': logistics_info.get('route_name'),
                'is_manual_date': True  # ÐœÐµÑ‚ÐºÐ°, Ñ‡Ñ‚Ð¾ Ð´Ð°Ñ‚Ñƒ Ð¸Ð·Ð¼ÐµÐ½Ð¸Ð»Ð¸ Ð²Ñ€ÑƒÑ‡Ð½ÑƒÑŽ
            }
            self.db.update_order(order_id, updates)

            logger.info(f"âœ“ Ð”Ð°Ñ‚Ð° Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð° Ð´Ð»Ñ {order_id}: {new_delivery_date}")

            # 4. Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ Ð’Ð¡Ð•Ð¥ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² Ð¾Ð± Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ð¸
            await self.sessions.broadcast_to_all({
                'type': 'order_update',
                'order_id': order_id,
                'update': updates
            })

            # 5. ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ð¿Ð¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð¸Ðµ Ð¸Ð½Ð¸Ñ†Ð¸Ð°Ñ‚Ð¾Ñ€Ñƒ (Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾)
            await self.safe_send(websocket, {
                'type': 'success',
                'message': f'Ð”Ð°Ñ‚Ð° Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð° Ð½Ð° {new_delivery_date}'
            })

        except Exception as e:
            logger.error(f"Error updating order date: {e}")
            # ÐŸÑ€Ð¾Ð±ÑƒÐµÐ¼ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð¾ÑˆÐ¸Ð±ÐºÑƒ, Ð½Ð¾ Ð½Ðµ Ð¿Ð°Ð´Ð°ÐµÐ¼ ÐµÑÐ»Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚ Ð¾Ñ‚ÐºÐ»ÑŽÑ‡Ð¸Ð»ÑÑ
            await self.safe_send(websocket, {
                'type': 'error',
                'message': f'ÐžÑˆÐ¸Ð±ÐºÐ° Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸Ñ Ð´Ð°Ñ‚Ñ‹: {str(e)}'
            })
        finally:
            if 'conn' in locals():
                conn.close()


    async def handle_get_next_delivery_date(self, websocket, data):
        """
        ÐŸÐžÐ›Ð£Ð§Ð•ÐÐ˜Ð• Ð¡Ð›Ð•Ð”Ð£Ð®Ð©Ð•Ð™ Ð”ÐÐ¢Ð«: Ð’Ñ‹Ñ‡Ð¸ÑÐ»ÑÐµÑ‚ ÑÐ»ÐµÐ´ÑƒÑŽÑ‰ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ Ð‘Ð•Ð— Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ Ð·Ð°ÐºÐ°Ð·Ð°.
        """
        order_id = data.get('order_id')
        if not order_id: return

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 1. ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ð° Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð° Ð¾Ð´Ð½Ð¸Ð¼ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð¼
            query = """
                SELECT
                    o.order_data,
                    cr.route_id,
                    lr.delivery_days,
                    lr.route_name
                FROM orders o
                LEFT JOIN client_routes cr ON json_extract(o.order_data, '$.kunden_nr') = cr.client_id
                LEFT JOIN logistics_routes lr ON cr.route_id = lr.route_id
                WHERE o.order_id = ?
            """
            cursor.execute(query, (order_id,))
            row = cursor.fetchone()

            if not row:
                await websocket.send(json.dumps({'type': 'error', 'message': 'Ð—Ð°ÐºÐ°Ð· Ð¸Ð»Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½'}))
                conn.close()
                return

            order_data_json = row[0]
            route_id = row[1] or 'free'
            delivery_days_json = row[2]
            route_name = row[3] or 'Ð¡Ð²Ð¾Ð±Ð¾Ð´Ð½Ñ‹Ð¹'

            order_data = json.loads(order_data_json)
            current_date_str = order_data.get('delivery_date')

            if not current_date_str:
                await websocket.send(json.dumps({'type': 'error', 'message': 'Ð£ Ð·Ð°ÐºÐ°Ð·Ð° Ð½ÐµÑ‚ Ð´Ð°Ñ‚Ñ‹ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸'}))
                conn.close()
                return

            current_date = datetime.strptime(current_date_str, "%Y-%m-%d").date()

            # 2. ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ ÑÐ¿Ð¸ÑÐ¾Ðº Ñ€Ð°Ð·Ñ€ÐµÑˆÐµÐ½Ð½Ñ‹Ñ… Ð´Ð½ÐµÐ¹ (0=ÐŸÐ½ ... 6=Ð’Ñ)
            allowed_days = []
            if delivery_days_json:
                try: allowed_days = json.loads(delivery_days_json)
                except: pass

            # Ð•ÑÐ»Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½ Ð¸Ð»Ð¸ Ð´Ð½Ð¸ Ð½Ðµ Ð·Ð°Ð´Ð°Ð½Ñ‹ -> Ð¿Ñ€Ð¾ÑÑ‚Ð¾ +1 Ð´ÐµÐ½ÑŒ
            if not allowed_days:
                allowed_days = [0, 1, 2, 3, 4, 5, 6] # Ð’ÑÐµ Ð´Ð½Ð¸

            # 3. Ð˜Ñ‰ÐµÐ¼ Ð¡Ð›Ð•Ð”Ð£Ð®Ð©Ð˜Ð™ Ð´ÐµÐ½ÑŒ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ Ð¿Ð¾ Ñ€Ð°ÑÐ¿Ð¸ÑÐ°Ð½Ð¸ÑŽ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°
            # Ð’ÐÐ–ÐÐž: Ð•ÑÐ»Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ Ð´Ð¾ÑÑ‚Ð°Ð²Ð»ÑÐµÑ‚ Ñ€Ð°Ð· Ð² Ð½ÐµÐ´ÐµÐ»ÑŽ (Ð½Ð°Ð¿Ñ€Ð¸Ð¼ÐµÑ€, Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ð¾ Ð¿ÑÑ‚Ð½Ð¸Ñ†Ð°Ð¼),
            # Ñ‚Ð¾ "ÑÐ»ÐµÐ´ÑƒÑŽÑ‰Ð¸Ð¹ Ñ€ÐµÐ¹Ñ" = ÑÐ»ÐµÐ´ÑƒÑŽÑ‰Ð°Ñ Ð¿ÑÑ‚Ð½Ð¸Ñ†Ð°, Ð¼Ð¸Ð½Ð¸Ð¼ÑƒÐ¼ Ñ‡ÐµÑ€ÐµÐ· 7 Ð´Ð½ÐµÐ¹

            # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼: ÑÑ‚Ð¾ Ð¾Ð´Ð¸Ð½Ð¾Ñ‡Ð½Ñ‹Ð¹ Ð´ÐµÐ½ÑŒ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ (Ñ€Ð°Ð· Ð² Ð½ÐµÐ´ÐµÐ»ÑŽ)?
            is_once_per_week = len(allowed_days) == 1

            if is_once_per_week:
                # ÐœÐ°Ñ€ÑˆÑ€ÑƒÑ‚ Ð´Ð¾ÑÑ‚Ð°Ð²Ð»ÑÐµÑ‚ Ñ€Ð°Ð· Ð² Ð½ÐµÐ´ÐµÐ»ÑŽ - Ð¸Ñ‰ÐµÐ¼ Ñ‚Ð¾Ñ‚ Ð¶Ðµ Ð´ÐµÐ½ÑŒ Ð½ÐµÐ´ÐµÐ»Ð¸ Ñ‡ÐµÑ€ÐµÐ· 7+ Ð´Ð½ÐµÐ¹
                target_weekday = allowed_days[0]
                next_date = current_date + timedelta(days=7)  # ÐœÐ¸Ð½Ð¸Ð¼ÑƒÐ¼ Ñ‡ÐµÑ€ÐµÐ· Ð½ÐµÐ´ÐµÐ»ÑŽ

                # ÐÐ°Ñ…Ð¾Ð´Ð¸Ð¼ Ð±Ð»Ð¸Ð¶Ð°Ð¹ÑˆÐ¸Ð¹ Ð½ÑƒÐ¶Ð½Ñ‹Ð¹ Ð´ÐµÐ½ÑŒ Ð½ÐµÐ´ÐµÐ»Ð¸ Ð¿Ð¾ÑÐ»Ðµ +7 Ð´Ð½ÐµÐ¹
                while next_date.weekday() != target_weekday:
                    next_date += timedelta(days=1)
                found = True
            else:
                # ÐœÐ°Ñ€ÑˆÑ€ÑƒÑ‚ Ð´Ð¾ÑÑ‚Ð°Ð²Ð»ÑÐµÑ‚ Ð½ÐµÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ñ€Ð°Ð· Ð² Ð½ÐµÐ´ÐµÐ»ÑŽ - Ð¸Ñ‰ÐµÐ¼ Ð±Ð»Ð¸Ð¶Ð°Ð¹ÑˆÐ¸Ð¹ ÑÐ»ÐµÐ´ÑƒÑŽÑ‰Ð¸Ð¹ Ð´ÐµÐ½ÑŒ
                next_date = current_date + timedelta(days=1)
                found = False

                # Ð˜Ñ‰ÐµÐ¼ Ð² Ñ‚ÐµÑ‡ÐµÐ½Ð¸Ðµ 14 Ð´Ð½ÐµÐ¹
                for _ in range(14):
                    if next_date.weekday() in allowed_days:
                        found = True
                        break
                    next_date += timedelta(days=1)

            if not found:
                await websocket.send(json.dumps({'type': 'error', 'message': 'ÐÐµ Ð½Ð°Ð¹Ð´ÐµÐ½ Ð¿Ð¾Ð´Ñ…Ð¾Ð´ÑÑ‰Ð¸Ð¹ Ð´ÐµÐ½ÑŒ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸'}))
                conn.close()
                return

            new_date_str = next_date.strftime('%Y-%m-%d')
            new_prod_date = (next_date - timedelta(days=1)).strftime('%Y-%m-%d')

            conn.close()

            # Ð’Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÐ¼ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÑŽ Ð¾ ÑÐ»ÐµÐ´ÑƒÑŽÑ‰ÐµÐ¹ Ð´Ð°Ñ‚Ðµ Ð‘Ð•Ð— Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ñ
            await websocket.send(json.dumps({
                'type': 'next_delivery_date',
                'order_id': order_id,
                'current_date': current_date_str,
                'next_date': new_date_str,
                'next_production_date': new_prod_date,
                'route_id': route_id,
                'route_name': route_name
            }))

        except Exception as e:
            logger.error(f"Get next delivery date error: {e}")
            if 'conn' in locals(): conn.close()

    async def handle_move_order_next_logistics(self, websocket, data):
        """
        Ð£ÐœÐÐ«Ð™ ÐŸÐ•Ð Ð•ÐÐžÐ¡: ÐÐ°Ñ…Ð¾Ð´Ð¸Ñ‚ ÑÐ»ÐµÐ´ÑƒÑŽÑ‰ÑƒÑŽ Ð²Ð°Ð»Ð¸Ð´Ð½ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ Ð¿Ð¾ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ñƒ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°.
        """
        order_id = data.get('order_id')
        if not order_id: return

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 1. ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ð° Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð° Ð¾Ð´Ð½Ð¸Ð¼ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð¼
            # ÐÐ°Ð¼ Ð½ÑƒÐ¶Ð½Ñ‹: Ñ‚ÐµÐºÑƒÑ‰Ð°Ñ Ð´Ð°Ñ‚Ð°, ID ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°, Ð´Ð½Ð¸ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°
            query = """
                SELECT
                    o.order_data,
                    cr.route_id,
                    lr.delivery_days
                FROM orders o
                LEFT JOIN client_routes cr ON json_extract(o.order_data, '$.kunden_nr') = cr.client_id
                LEFT JOIN logistics_routes lr ON cr.route_id = lr.route_id
                WHERE o.order_id = ?
            """
            cursor.execute(query, (order_id,))
            row = cursor.fetchone()

            if not row:
                await websocket.send(json.dumps({'type': 'error', 'message': 'Ð—Ð°ÐºÐ°Ð· Ð¸Ð»Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½'}))
                conn.close()
                return

            order_data_json = row[0]
            route_id = row[1]
            delivery_days_json = row[2]

            order_data = json.loads(order_data_json)
            current_date_str = order_data.get('delivery_date')

            if not current_date_str:
                conn.close()
                return

            current_date = datetime.strptime(current_date_str, "%Y-%m-%d").date()

            # 2. ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ ÑÐ¿Ð¸ÑÐ¾Ðº Ñ€Ð°Ð·Ñ€ÐµÑˆÐµÐ½Ð½Ñ‹Ñ… Ð´Ð½ÐµÐ¹ (0=ÐŸÐ½ ... 6=Ð’Ñ)
            allowed_days = []
            if delivery_days_json:
                try: allowed_days = json.loads(delivery_days_json)
                except: pass

            # Ð•ÑÐ»Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½ Ð¸Ð»Ð¸ Ð´Ð½Ð¸ Ð½Ðµ Ð·Ð°Ð´Ð°Ð½Ñ‹ -> Ð¿Ñ€Ð¾ÑÑ‚Ð¾ +1 Ð´ÐµÐ½ÑŒ
            if not allowed_days:
                allowed_days = [0, 1, 2, 3, 4, 5, 6] # Ð’ÑÐµ Ð´Ð½Ð¸

            # 3. Ð˜Ñ‰ÐµÐ¼ Ð¡Ð›Ð•Ð”Ð£Ð®Ð©Ð˜Ð™ Ð´ÐµÐ½ÑŒ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ Ð¿Ð¾ Ñ€Ð°ÑÐ¿Ð¸ÑÐ°Ð½Ð¸ÑŽ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°
            # Ð’ÐÐ–ÐÐž: Ð•ÑÐ»Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ Ð´Ð¾ÑÑ‚Ð°Ð²Ð»ÑÐµÑ‚ Ñ€Ð°Ð· Ð² Ð½ÐµÐ´ÐµÐ»ÑŽ (Ð½Ð°Ð¿Ñ€Ð¸Ð¼ÐµÑ€, Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ð¾ Ð¿ÑÑ‚Ð½Ð¸Ñ†Ð°Ð¼),
            # Ñ‚Ð¾ "ÑÐ»ÐµÐ´ÑƒÑŽÑ‰Ð¸Ð¹ Ñ€ÐµÐ¹Ñ" = ÑÐ»ÐµÐ´ÑƒÑŽÑ‰Ð°Ñ Ð¿ÑÑ‚Ð½Ð¸Ñ†Ð°, Ð¼Ð¸Ð½Ð¸Ð¼ÑƒÐ¼ Ñ‡ÐµÑ€ÐµÐ· 7 Ð´Ð½ÐµÐ¹

            # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼: ÑÑ‚Ð¾ Ð¾Ð´Ð¸Ð½Ð¾Ñ‡Ð½Ñ‹Ð¹ Ð´ÐµÐ½ÑŒ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ (Ñ€Ð°Ð· Ð² Ð½ÐµÐ´ÐµÐ»ÑŽ)?
            is_once_per_week = len(allowed_days) == 1

            if is_once_per_week:
                # ÐœÐ°Ñ€ÑˆÑ€ÑƒÑ‚ Ð´Ð¾ÑÑ‚Ð°Ð²Ð»ÑÐµÑ‚ Ñ€Ð°Ð· Ð² Ð½ÐµÐ´ÐµÐ»ÑŽ - Ð¸Ñ‰ÐµÐ¼ Ñ‚Ð¾Ñ‚ Ð¶Ðµ Ð´ÐµÐ½ÑŒ Ð½ÐµÐ´ÐµÐ»Ð¸ Ñ‡ÐµÑ€ÐµÐ· 7+ Ð´Ð½ÐµÐ¹
                target_weekday = allowed_days[0]
                next_date = current_date + timedelta(days=7)  # ÐœÐ¸Ð½Ð¸Ð¼ÑƒÐ¼ Ñ‡ÐµÑ€ÐµÐ· Ð½ÐµÐ´ÐµÐ»ÑŽ

                # ÐÐ°Ñ…Ð¾Ð´Ð¸Ð¼ Ð±Ð»Ð¸Ð¶Ð°Ð¹ÑˆÐ¸Ð¹ Ð½ÑƒÐ¶Ð½Ñ‹Ð¹ Ð´ÐµÐ½ÑŒ Ð½ÐµÐ´ÐµÐ»Ð¸ Ð¿Ð¾ÑÐ»Ðµ +7 Ð´Ð½ÐµÐ¹
                while next_date.weekday() != target_weekday:
                    next_date += timedelta(days=1)
                found = True
            else:
                # ÐœÐ°Ñ€ÑˆÑ€ÑƒÑ‚ Ð´Ð¾ÑÑ‚Ð°Ð²Ð»ÑÐµÑ‚ Ð½ÐµÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ñ€Ð°Ð· Ð² Ð½ÐµÐ´ÐµÐ»ÑŽ - Ð¸Ñ‰ÐµÐ¼ Ð±Ð»Ð¸Ð¶Ð°Ð¹ÑˆÐ¸Ð¹ ÑÐ»ÐµÐ´ÑƒÑŽÑ‰Ð¸Ð¹ Ð´ÐµÐ½ÑŒ
                next_date = current_date + timedelta(days=1)
                found = False

                # Ð˜Ñ‰ÐµÐ¼ Ð² Ñ‚ÐµÑ‡ÐµÐ½Ð¸Ðµ 14 Ð´Ð½ÐµÐ¹
                for _ in range(14):
                    if next_date.weekday() in allowed_days:
                        found = True
                        break
                    next_date += timedelta(days=1)

            if not found:
                await websocket.send(json.dumps({'type': 'error', 'message': 'ÐÐµ Ð½Ð°Ð¹Ð´ÐµÐ½ Ð¿Ð¾Ð´Ñ…Ð¾Ð´ÑÑ‰Ð¸Ð¹ Ð´ÐµÐ½ÑŒ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸'}))
                conn.close()
                return

            new_date_str = next_date.strftime('%Y-%m-%d')

            # 4. ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ Ð·Ð°ÐºÐ°Ð·
            # Ð¡Ñ‡Ð¸Ñ‚Ð°ÐµÐ¼ Ð½Ð¾Ð²ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð° (Ð¿Ð¾ Ð´ÐµÑ„Ð¾Ð»Ñ‚Ñƒ -1 Ð´ÐµÐ½ÑŒ, Ð¸Ð»Ð¸ Ð¿ÐµÑ€ÐµÑÑ‡Ð¸Ñ‚Ð°ÐµÑ‚ Ð»Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÐ° Ð¿Ð¾Ð·Ð¶Ðµ)
            # Ð”Ð»Ñ Ð¿Ñ€Ð¾ÑÑ‚Ð¾Ñ‚Ñ‹ Ð¿Ð¾ÐºÐ° ÑÑ‚Ð°Ð²Ð¸Ð¼ production = delivery - 1
            new_prod_date = (next_date - timedelta(days=1)).strftime('%Y-%m-%d')

            # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ JSON Ð¸ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸
            order_data['delivery_date'] = new_date_str
            order_data['production_date'] = new_prod_date

            cursor.execute('''
                UPDATE orders
                SET order_data = ?, delivery_date = ?, production_date = ?, updated_at = ?
                WHERE order_id = ?
            ''', (json.dumps(order_data), new_date_str, new_prod_date, datetime.now().isoformat(), order_id))

            conn.commit()
            conn.close()

            logger.info(f"ðŸšš Ð—Ð°ÐºÐ°Ð· {order_id} Ð¿ÐµÑ€ÐµÐ½ÐµÑÐµÐ½ Ñ {current_date_str} Ð½Ð° {new_date_str} (ÐœÐ°Ñ€ÑˆÑ€ÑƒÑ‚: {route_id})")

            # 5. Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ Ð²ÑÐµÑ…
            await self.sessions.broadcast_to_all({
                'type': 'order_update',
                'order_id': order_id,
                'update': {
                    'delivery_date': new_date_str,
                    'production_date': new_prod_date
                }
            })

            # ÐŸÐ¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð¸Ðµ Ð¸Ð½Ð¸Ñ†Ð¸Ð°Ñ‚Ð¾Ñ€Ñƒ
            await websocket.send(json.dumps({
                'type': 'success',
                'message': f'ÐŸÐµÑ€ÐµÐ½ÐµÑÐµÐ½Ð¾ Ð½Ð° {new_date_str} ({route_id})'
            }))

        except Exception as e:
            logger.error(f"Move order error: {e}")
            if 'conn' in locals(): conn.close()                    

    async def handle_get_overdue_orders_preview(self, websocket, data):
        """
        Ð’Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ ÑÐ¿Ð¸ÑÐ¾Ðº Ð¿Ñ€Ð¾ÑÑ€Ð¾Ñ‡ÐµÐ½Ð½Ñ‹Ñ… (Ð¿Ñ€Ð¾ÑˆÐ»Ñ‹Ñ…) Ð½ÐµÐ¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚Ð°Ð½Ð½Ñ‹Ñ… Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
        Ñ Ð¿Ñ€ÐµÐ´Ð»Ð°Ð³Ð°ÐµÐ¼Ñ‹Ð¼Ð¸ Ð½Ð¾Ð²Ñ‹Ð¼Ð¸ Ð´Ð°Ñ‚Ð°Ð¼Ð¸ Ð¿Ð¾ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ñƒ ÐºÐ°Ð¶Ð´Ð¾Ð³Ð¾ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°.
        """
        today = datetime.now().date()
        today_str = today.strftime('%Y-%m-%d')

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    o.order_id,
                    o.order_data,
                    o.delivery_date,
                    o.status,
                    COALESCE(cr.route_id, 'free') AS route_id,
                    COALESCE(lr.route_name, 'Ð¡Ð²Ð¾Ð±Ð¾Ð´Ð½Ñ‹Ð¹') AS route_name,
                    lr.delivery_days
                FROM orders o
                LEFT JOIN client_routes cr ON json_extract(o.order_data, '$.kunden_nr') = cr.client_id
                LEFT JOIN logistics_routes lr ON cr.route_id = lr.route_id
                WHERE o.delivery_date < ?
                  AND o.status NOT IN ('completed', 'archived')
                  AND COALESCE(json_extract(o.order_data, '$.printed'), 0) = 0
                  AND COALESCE(json_extract(o.order_data, '$.invoice_status'), '') NOT LIKE '%âœ…%'
                  AND COALESCE(CAST(json_extract(o.order_data, '$.boxes_count') AS INTEGER), 0) = 0
                ORDER BY o.delivery_date ASC
            """, (today_str,))
            rows = cursor.fetchall()

            result = []
            for row in rows:
                order_id = row[0]
                order_data = json.loads(row[1])
                current_date_str = row[2]
                route_id = row[4]
                route_name = row[5]
                delivery_days_json = row[6]

                allowed_days = []
                if delivery_days_json:
                    try:
                        allowed_days = json.loads(delivery_days_json)
                    except Exception:
                        pass

                # Ð’Ñ‹Ñ‡Ð¸ÑÐ»ÑÐµÐ¼ ÑÐ»ÐµÐ´ÑƒÑŽÑ‰ÑƒÑŽ Ð²Ð°Ð»Ð¸Ð´Ð½ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ Ñ ÑÐµÐ³Ð¾Ð´Ð½Ñ
                base = today
                if not allowed_days:
                    next_date = base + timedelta(days=1)
                elif len(allowed_days) == 1:
                    target_wd = allowed_days[0]
                    next_date = base + timedelta(days=1)
                    for _ in range(14):
                        if next_date.weekday() == target_wd:
                            break
                        next_date += timedelta(days=1)
                else:
                    next_date = base + timedelta(days=1)
                    for _ in range(14):
                        if next_date.weekday() in allowed_days:
                            break
                        next_date += timedelta(days=1)

                proposed_date = next_date.strftime('%Y-%m-%d')
                prod_date = (next_date - timedelta(days=1)).strftime('%Y-%m-%d')

                result.append({
                    'order_id': order_id,
                    'kunde': order_data.get('kunde', ''),
                    'kunden_nr': order_data.get('kunden_nr', ''),
                    'current_date': current_date_str,
                    'proposed_date': proposed_date,
                    'proposed_prod_date': prod_date,
                    'route_id': route_id,
                    'route_name': route_name,
                    'artikel': order_data.get('artikel', []),
                    'total_value': order_data.get('total_value', 0),
                    'status': row[3],
                })

            await websocket.send(json.dumps({
                'type': 'overdue_orders_preview',
                'orders': result,
            }))

        except Exception as e:
            logger.error(f"handle_get_overdue_orders_preview error: {e}")
        finally:
            conn.close()

    async def handle_bulk_reschedule_orders(self, websocket, data):
        """
        ÐœÐ°ÑÑÐ¾Ð²Ñ‹Ð¹ Ð¿ÐµÑ€ÐµÐ½Ð¾Ñ Ð·Ð°ÐºÐ°Ð·Ð¾Ð² Ð½Ð° Ð½Ð¾Ð²Ñ‹Ðµ Ð´Ð°Ñ‚Ñ‹.
        ÐŸÑ€Ð¸Ð½Ð¸Ð¼Ð°ÐµÑ‚ ÑÐ¿Ð¸ÑÐ¾Ðº {order_id, proposed_date, proposed_prod_date}.
        """
        items = data.get('items', [])  # [{order_id, proposed_date, proposed_prod_date}, ...]
        if not items:
            return

        moved = []
        errors = []
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            for item in items:
                order_id = item.get('order_id')
                new_date_str = item.get('proposed_date')
                new_prod_str = item.get('proposed_prod_date')
                if not order_id or not new_date_str:
                    continue
                try:
                    cursor.execute('SELECT order_data FROM orders WHERE order_id = ?', (order_id,))
                    row = cursor.fetchone()
                    if not row:
                        errors.append(order_id)
                        continue

                    order_data = json.loads(row[0])
                    order_data['delivery_date'] = new_date_str
                    order_data['production_date'] = new_prod_str or new_date_str

                    cursor.execute('''
                        UPDATE orders
                        SET order_data = ?, delivery_date = ?, production_date = ?, updated_at = ?
                        WHERE order_id = ?
                    ''', (json.dumps(order_data), new_date_str, order_data['production_date'],
                          datetime.now().isoformat(), order_id))

                    moved.append({'order_id': order_id, 'new_date': new_date_str})
                except Exception as e:
                    logger.error(f"bulk_reschedule: error on {order_id}: {e}")
                    errors.append(order_id)

            conn.commit()

        except Exception as e:
            logger.error(f"handle_bulk_reschedule_orders error: {e}")
        finally:
            conn.close()

        # ÐžÐ¿Ð¾Ð²ÐµÑ‰Ð°ÐµÐ¼ Ð²ÑÐµÑ… ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² Ð¾Ð± Ð¸Ð·Ð¼ÐµÐ½ÐµÐ½Ð¸ÑÑ…
        for m in moved:
            await self.sessions.broadcast_to_all({
                'type': 'order_update',
                'order_id': m['order_id'],
                'update': {'delivery_date': m['new_date']},
            })

        await websocket.send(json.dumps({
            'type': 'bulk_reschedule_done',
            'moved': len(moved),
            'errors': len(errors),
            'message': f"ÐŸÐµÑ€ÐµÐ½ÐµÑÐµÐ½Ð¾ {len(moved)} Ð·Ð°ÐºÐ°Ð·Ð¾Ð²" + (f", Ð¾ÑˆÐ¸Ð±Ð¾Ðº: {len(errors)}" if errors else ""),
        }))
        logger.info(f"bulk_reschedule: moved={len(moved)} errors={len(errors)}")

    async def handle_recalc_order_logistics(self, websocket, data):
        """ÐŸÑ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ð¹ Ð¿ÐµÑ€ÐµÑÑ‡ÐµÑ‚ Ð»Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÐ¸ Ð´Ð»Ñ Ð·Ð°ÐºÐ°Ð·Ð°"""
        order_id = data.get('order_id')
        
        # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð·Ð°ÐºÐ°Ð·
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT order_data FROM orders WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row: return
        
        order_data = json.loads(row[0])
        
        # Ð’Ñ‹Ð·Ñ‹Ð²Ð°ÐµÐ¼ Ð»Ð¾Ð³Ð¸ÑÑ‚Ð° Ð·Ð°Ð½Ð¾Ð²Ð¾
        # Ð‘ÐµÑ€ÐµÐ¼ Ð´Ð°Ñ‚Ñƒ Ð¡ÐžÐ—Ð”ÐÐÐ˜Ð¯ Ð·Ð°ÐºÐ°Ð·Ð° ÐºÐ°Ðº Ñ‚Ð¾Ñ‡ÐºÑƒ Ð¾Ñ‚ÑÑ‡ÐµÑ‚Ð°
        order_date = order_data.get('date', datetime.now().strftime("%Y-%m-%d"))
        kunden_nr = order_data.get('kunden_nr')
        
        logistics_info = self.logistics_manager.calculate_dates(order_date, kunden_nr)
        
        # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼
        updates = {
            'delivery_date': logistics_info['delivery_date'],
            'production_date': logistics_info['production_date'],
            'route_id': logistics_info['route_id'],
            'route_name': logistics_info['route_name'],
            'is_manual_date': False # Ð¡Ð±Ñ€Ð°ÑÑ‹Ð²Ð°ÐµÐ¼ Ñ€ÑƒÑ‡Ð½Ð¾Ð¹ Ñ„Ð»Ð°Ð³
        }
        
        self.db.update_order(order_id, updates)
        
        await self.sessions.broadcast_to_all({
            'type': 'order_update',
            'order_id': order_id,
            'update': updates
        })
        logger.info(f"Logistics recalculated for {order_id}: {logistics_info['delivery_date']}")

    # ============================================================
    # ÐÐžÐ’ÐÐ¯ Ð›ÐžÐ“Ð˜ÐšÐ ÐŸÐ ÐžÐ˜Ð—Ð’ÐžÐ”Ð¡Ð¢Ð’Ð (CAPACITY-BASED / SMART PULL)
    # ============================================================
    # Production planning methods moved to backend/production_planner.py


    
    def get_historical_forecast(self, article_nr, target_date):
        """
        Ð˜Ñ‰ÐµÑ‚ Ð¿Ñ€Ð¾Ð´Ð°Ð¶Ð¸ Ð¢ÐžÐ§ÐÐž Ð·Ð° ÑÑ‚Ð¾Ñ‚ Ð¶Ðµ Ð´ÐµÐ½ÑŒ Ð³Ð¾Ð´ Ð½Ð°Ð·Ð°Ð´ (Ð´Ð»Ñ Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·Ð°)
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Ð’Ñ‹Ñ‡Ð¸ÑÐ»ÑÐµÐ¼ Ð´Ð°Ñ‚Ñƒ Ð³Ð¾Ð´ Ð½Ð°Ð·Ð°Ð´ (ÑƒÑ‡Ð¸Ñ‚Ñ‹Ð²Ð°ÐµÐ¼ Ð²Ð¸ÑÐ¾ÐºÐ¾ÑÐ½Ñ‹Ðµ Ð³Ð¾Ð´Ñ‹)
            try:
                last_year_date = target_date.replace(year=target_date.year - 1)
            except ValueError:
                # Ð•ÑÐ»Ð¸ ÑÐµÐ³Ð¾Ð´Ð½Ñ 29 Ñ„ÐµÐ²Ñ€Ð°Ð»Ñ, Ð° Ð³Ð¾Ð´ Ð½Ð°Ð·Ð°Ð´ ÐµÐ³Ð¾ Ð½Ðµ Ð±Ñ‹Ð»Ð¾, Ð±ÐµÑ€ÐµÐ¼ 28
                last_year_date = target_date.replace(year=target_date.year - 1, day=28)
                
            last_year_str = last_year_date.strftime('%Y-%m-%d')

            # Ð˜Ñ‰ÐµÐ¼ Ð¿Ñ€Ð¾Ð´Ð°Ð¶Ð¸ Ð² Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ð¸
            cursor.execute("""
                SELECT SUM(quantity) FROM sales_history
                WHERE article_nr = ? AND sale_date = ?
            """, (article_nr, last_year_str))

            res = cursor.fetchone()[0]
            result = float(res) if res else 0.0
            
            return result
        except Exception as e:
            logger.error(f"Forecast error: {e}")
            return 0.0
        finally:
            conn.close()

    def get_weekly_historical_forecast(self, article_nr, week_start_date):
        """
        ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð· Ð¿Ñ€Ð¾Ð´Ð°Ð¶ Ð½Ð° Ð½ÐµÐ´ÐµÐ»ÑŽ Ð½Ð° Ð¾ÑÐ½Ð¾Ð²Ðµ Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ð¸ Ð³Ð¾Ð´ Ð½Ð°Ð·Ð°Ð´
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            try:
                last_year_start = week_start_date.replace(year=week_start_date.year - 1)
            except ValueError:
                last_year_start = week_start_date.replace(year=week_start_date.year - 1, day=28)
                
            last_year_end = last_year_start + timedelta(days=6)

            cursor.execute("""
                SELECT SUM(quantity) FROM sales_history
                WHERE article_nr = ? AND sale_date BETWEEN ? AND ?
            """, (article_nr, last_year_start.strftime('%Y-%m-%d'), last_year_end.strftime('%Y-%m-%d')))

            res = cursor.fetchone()[0]
            return float(res) if res else 0.0
        except Exception as e:
            logger.error(f"Weekly forecast error: {e}")
            return 0.0
        finally:
            conn.close()

    # ============================================================
    # Ð•Ð”Ð˜ÐÐžÐ• Ð¯Ð”Ð Ðž Ð ÐÐ¡Ð§Ð•Ð¢Ð (CORE LOGIC)
    # ============================================================
    def _calculate_core_plan(self, start_date_obj, user_id):
        """
        Ð•Ð´Ð¸Ð½Ñ‹Ð¹ Ð°Ð»Ð³Ð¾Ñ€Ð¸Ñ‚Ð¼ Ñ€Ð°ÑÑ‡ÐµÑ‚Ð° Ð´Ð»Ñ Ð”Ð½ÐµÐ²Ð½Ð¾Ð³Ð¾ Ð¸ ÐÐµÐ´ÐµÐ»ÑŒÐ½Ð¾Ð³Ð¾ Ð¿Ð»Ð°Ð½Ð°.
        Ð“Ð°Ñ€Ð°Ð½Ñ‚Ð¸Ñ€ÑƒÐµÑ‚, Ñ‡Ñ‚Ð¾ Ñ†Ð¸Ñ„Ñ€Ñ‹ Ð²ÑÐµÐ³Ð´Ð° ÑÐ¾Ð²Ð¿Ð°Ð´Ð°ÑŽÑ‚.
        Ð’ÑÑ‚Ñ€Ð¾ÐµÐ½Ð½Ñ‹Ð¹ ÐºÑÑˆ: Ð¿Ð¾Ð²Ñ‚Ð¾Ñ€Ð½Ñ‹Ð¹ Ð²Ñ‹Ð·Ð¾Ð² Ñ Ñ‚ÐµÐ¼ Ð¶Ðµ week_start Ð² Ñ‚ÐµÑ‡ÐµÐ½Ð¸Ðµ 10Ñ Ð²Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ ÐºÑÑˆ.
        """
        import math

        # 1. ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ Ð³Ñ€Ð°Ð½Ð¸Ñ†Ñ‹ Ð½ÐµÐ´ÐµÐ»Ð¸
        week_start = start_date_obj - timedelta(days=start_date_obj.weekday())
        week_end = week_start + timedelta(days=6)

        # Throttle: ÐµÑÐ»Ð¸ Ñ‚Ð¾Ñ‚ Ð¶Ðµ Ð¿Ð»Ð°Ð½ ÑÑ‡Ð¸Ñ‚Ð°Ð»ÑÑ <10Ñ Ð½Ð°Ð·Ð°Ð´ â€” Ð²Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÐ¼ ÐºÑÑˆ
        cache_key = week_start.strftime('%Y-%m-%d')
        now = time.time()
        if not hasattr(self, '_plan_cache'):
            self._plan_cache = {}
        cached = self._plan_cache.get(cache_key)
        if cached and (now - cached['ts']) < 10:
            logger.debug(f"[PLAN] Cache hit for {cache_key} ({now - cached['ts']:.1f}s ago)")
            return cached['result']
    
        # 2. ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¸ Ð‘Ð°Ð·Ð°
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
        
            # Ð Ð°Ð±Ð¾Ñ‡Ð¸Ðµ Ð´Ð½Ð¸ (Ð±ÐµÑ€Ñ‘Ð¼ Ð³Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ñ user_id IS NULL)
            try:
                cursor.execute("SELECT setting_value FROM plan_settings WHERE setting_key='workdays' AND user_id IS NULL")
                row = cursor.fetchone()
                workdays_list = json.loads(row[0]) if row else []
                logger.info(f"[PLAN] Loaded workdays from DB: {workdays_list}")
            except Exception as e:
                logger.warning(f"[PLAN] Failed to load workdays: {e}")
                workdays_list = []
            if not workdays_list: workdays_list = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
        
            day_map = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6}
            enabled_days = sorted([day_map[d.lower()] for d in workdays_list if d.lower() in day_map])
            num_workdays = len(enabled_days) or 5
            is_five_day_mode = enabled_days == [0, 1, 2, 3, 4]
            logger.info(f"[PLAN] Distribution: {num_workdays} workdays, enabled_days={enabled_days}")

            # Ð”Ð°Ð½Ð½Ñ‹Ðµ Ð¸Ð· Ð‘Ð”
            cursor.execute("SELECT * FROM factory_resources")
            resources_map = {int(r['resource_id']): dict(r) for r in cursor.fetchall()}

            cursor.execute("SELECT * FROM dough_types")
            components_db = {row['dough_id']: dict(row) for row in cursor.fetchall()}
        
            comp_name_lookup = {}
            for d_id, val in components_db.items():
                clean = str(val['name']).lower().replace(" ", "").replace("-", "")
                comp_name_lookup[clean] = d_id

            recipes = {}
            recipe_names = {}
            cursor.execute("SELECT * FROM recipes WHERE active = 1")
            for row in cursor.fetchall():
                art = str(row['article_nr']).strip().zfill(5)
                recipes[art] = dict(row)
                recipe_names[art] = row['name']

            all_orders = self.db.get_all_orders()
        
            # Ð”Ð¾Ð¿. Ñ€ÐµÑÑƒÑ€ÑÑ‹ (ÑÐ±Ð¾Ñ€ÐºÐ°)
            extra_resources = {}
            try:
                cursor.execute("SELECT article_nr, resource_id, time_needed_min FROM product_resource_consumption")
                for row in cursor.fetchall():
                    an = str(row['article_nr']).strip().zfill(5)
                    rid = int(row['resource_id'])
                    if an not in extra_resources: extra_resources[an] = {}
                    extra_resources[an][rid] = float(row['time_needed_min'])
            except: pass

            # --- ÐŸÐ ÐžÐ“ÐÐžÐ— (Ð˜Ð¡Ð¢ÐžÐ Ð˜Ð¯) ---
            weekly_forecast = {}
            try:
                curr_year, curr_week, _ = week_start.isocalendar()
                last_year = curr_year - 1
                cursor.execute("SELECT article_nr, quantity FROM weekly_sales_history WHERE year=? AND week=?", (last_year, curr_week))
                for row in cursor.fetchall():
                    art = str(row['article_nr']).strip().zfill(5)
                    qty = float(row['quantity']) if row['quantity'] else 0
                    if qty > 0: weekly_forecast[art] = int(qty) # Ð§Ð¸ÑÑ‚Ñ‹Ð¹ Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð· (Ð±ÑƒÑ„ÐµÑ€ +10% Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÑ‚ÑÑ Ð² Ñ„Ð¾Ñ€Ð¼ÑƒÐ»Ðµ Ñ€Ð°ÑÑ‡Ñ‘Ñ‚Ð°)
            except: pass

            # --- ÐžÐ¡Ð¢ÐÐ¢ÐšÐ˜ (Ð±ÐµÑ€Ñ‘Ð¼ ÐŸÐžÐ¡Ð›Ð•Ð”ÐÐ˜Ð• Ð Ð£Ð§ÐÐ«Ð• Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð”Ð›Ð¯ ÐšÐÐ–Ð”ÐžÐ“Ðž Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð°) ---
            # Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ Ð¢ÐžÐ›Ð¬ÐšÐž Ð·Ð°Ð¿Ð¸ÑÐ¸ Ð¾Ñ‚ Ñ€ÐµÐ°Ð»ÑŒÐ½Ñ‹Ñ… Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¹ (last_editor != 'System')
            # System-Ð·Ð°Ð¿Ð¸ÑÐ¸ â€” ÑÑ‚Ð¾ Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·Ñ‹/Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸, Ð¾Ð½Ð¸ Ð½Ðµ Ð´Ð¾Ð»Ð¶Ð½Ñ‹ Ð¿Ð¾Ð´Ð¼ÐµÐ½ÑÑ‚ÑŒ Ñ€ÐµÐ°Ð»ÑŒÐ½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ ÑÐºÐ»Ð°Ð´Ð°
            current_stock = {}
            try:
                stock_cutoff = week_end.strftime('%Y-%m-%d')
                cursor.execute("""
                    SELECT d.article_nr, d.quantity
                    FROM daily_stock_reports d
                    WHERE d.date = (
                        SELECT MAX(d2.date)
                        FROM daily_stock_reports d2
                        WHERE d2.article_nr = d.article_nr
                        AND d2.date <= ?
                        AND d2.last_editor IS NOT NULL
                        AND d2.last_editor != 'System'
                    )
                """, (stock_cutoff,))
                for row in cursor.fetchall():
                    current_stock[str(row[0]).strip().zfill(5)] = float(row[1])
            except: pass

        # 3. Ð ÐÐ¡Ð§Ð•Ð¢ ÐŸÐžÐ¢Ð Ð•Ð‘ÐÐžÐ¡Ð¢Ð˜ - ÐŸÐ ÐžÐ¡Ð¢ÐÐ¯ Ð›ÐžÐ“Ð˜ÐšÐ
        # ============================================================
        # Ð¤Ð¾Ñ€Ð¼ÑƒÐ»Ð°: MAX(Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·, Ð·Ð°ÐºÐ°Ð·Ñ‹) * 1.10 - Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ðº + Ð¼Ð¸Ð½.Ð·Ð°Ð¿Ð°Ñ
        # ============================================================

        # Ð¡Ð¾Ð±Ð¸Ñ€Ð°ÐµÐ¼ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ð½Ð° Ð½ÐµÐ´ÐµÐ»ÑŽ
        weekly_orders_total = {}
        next_monday_orders = {}
        next_monday_date = week_end + timedelta(days=1)
        for order in all_orders:
            d_str = order.get('delivery_date')
            if not d_str: continue
            try: d_date = datetime.strptime(d_str, "%Y-%m-%d").date()
            except: continue

            # Ð”Ð»Ñ 5-Ð´Ð½ÐµÐ²ÐºÐ¸:
            # - Ð½ÐµÐ´ÐµÐ»ÑŒÐ½Ñ‹Ð¹ Ð¾Ð±ÑŠÑ‘Ð¼ ÑÑ‡Ð¸Ñ‚Ð°ÐµÐ¼ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ð¾ Ñ‚ÐµÐºÑƒÑ‰ÐµÐ¹ Ð½ÐµÐ´ÐµÐ»Ðµ (ÐŸÐ½..Ð’Ñ)
            # - Ð·Ð°ÐºÐ°Ð·Ñ‹ ÑÐ»ÐµÐ´ÑƒÑŽÑ‰ÐµÐ³Ð¾ Ð¿Ð¾Ð½ÐµÐ´ÐµÐ»ÑŒÐ½Ð¸ÐºÐ° Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾ Ð¿ÐµÑ€ÐµÐ½Ð¾ÑÐ¸Ð¼ Ð½Ð° Ð¿ÑÑ‚Ð½Ð¸Ñ†Ñƒ.
            if is_five_day_mode:
                if week_start <= d_date <= week_end:
                    target_map = weekly_orders_total
                elif d_date == next_monday_date:
                    target_map = next_monday_orders
                else:
                    continue
            else:
                # Ð˜ÑÑ‚Ð¾Ñ€Ð¸Ñ‡ÐµÑÐºÐ¾Ðµ Ð¿Ð¾Ð²ÐµÐ´ÐµÐ½Ð¸Ðµ: Ñ‚ÐµÐºÑƒÑ‰Ð°Ñ Ð½ÐµÐ´ÐµÐ»Ñ + ÑÐ»ÐµÐ´ÑƒÑŽÑ‰Ð¸Ð¹ Ð¿Ð¾Ð½ÐµÐ´ÐµÐ»ÑŒÐ½Ð¸Ðº.
                if not (week_start <= d_date <= week_end + timedelta(days=1)):
                    continue
                target_map = weekly_orders_total

            for art in order.get('artikel', []):
                an = str(art.get('artikel_nr') or art.get('nummer', '')).strip().zfill(5)
                qty = float(art.get('menge', 0))
                if qty > 0:
                    target_map[an] = target_map.get(an, 0) + qty

        # Ð’ÑÐµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñ‹ (Ð¸Ð· Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·Ð° + Ð¸Ð· Ð·Ð°ÐºÐ°Ð·Ð¾Ð²)
        all_articles = set(recipes.keys()) | set(weekly_forecast.keys()) | set(weekly_orders_total.keys())
        if is_five_day_mode:
            all_articles |= set(next_monday_orders.keys())

        # ============================================================
        # 4. ÐŸÐ ÐžÐ¡Ð¢ÐžÐ™ Ð ÐÐ¡Ð§Ð•Ð¢ ÐŸÐ›ÐÐÐ - MAX(Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·, Ð·Ð°ÐºÐ°Ð·Ñ‹) * 1.10 - Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ðº
        # ============================================================
        plan_by_day = {i: {} for i in range(7)}

        def round_to_batch(qty, art_nr):
            """ÐžÐºÑ€ÑƒÐ³Ð»ÐµÐ½Ð¸Ðµ Ð´Ð¾ Ñ€Ð°Ð·Ð¼ÐµÑ€Ð° Ð¿Ð°Ñ€Ñ‚Ð¸Ð¸"""
            rec = recipes.get(art_nr, {})
            min_batch = int(rec.get('min_batch_size', 1) or 1)
            if min_batch <= 1 or qty <= 0:
                return max(0, int(qty))
            batches = math.ceil(qty / min_batch)
            return batches * min_batch

        for art in all_articles:
            if art not in recipes:
                continue

            rec = recipes[art]
            forecast = weekly_forecast.get(art, 0)
            orders = weekly_orders_total.get(art, 0)
            stock = current_stock.get(art, 0)
            min_stock = float(rec.get('min_stock_level', 0) or 0)
            min_batch = int(rec.get('min_batch_size', 1) or 1)

            # Ð¤ÐžÐ ÐœÐ£Ð›Ð: MAX(Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·, Ð·Ð°ÐºÐ°Ð·Ñ‹) * 1.10 - Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ðº + Ð¼Ð¸Ð½.Ð·Ð°Ð¿Ð°Ñ
            base_need = max(forecast, orders)
            weekly_need = math.ceil(base_need * 1.10)  # +10%
            weekly_to_produce = weekly_need - stock + min_stock

            if is_five_day_mode:
                # 1) ÐžÐ±Ñ‹Ñ‡Ð½Ñ‹Ð¹ Ð½ÐµÐ´ÐµÐ»ÑŒÐ½Ñ‹Ð¹ Ð¾Ð±ÑŠÑ‘Ð¼ (Ð±ÐµÐ· Ð¼Ð¸Ð½Ð¸Ð¼Ð°Ð»ÑŒÐ½Ð¾Ð³Ð¾ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ°) -> Ñ‚Ð¾Ð»ÑŒÐºÐ¾ ÐŸÐ½..Ð§Ñ‚.
                mon_thu_days = [d for d in enabled_days if d != 4]
                regular_weekly_qty = max(0, weekly_need - stock)
                regular_weekly_qty = round_to_batch(regular_weekly_qty, art)

                if regular_weekly_qty > 0 and mon_thu_days:
                    total_batches = math.ceil(regular_weekly_qty / min_batch) if min_batch > 0 else 1
                    batches_per_day = total_batches // len(mon_thu_days)
                    extra_batches = total_batches % len(mon_thu_days)

                    if art in list(all_articles)[:3]:
                        logger.info(
                            f"[PLAN] Art {art} 5day regular: qty={regular_weekly_qty}, "
                            f"days={mon_thu_days}, batches={total_batches}, per_day={batches_per_day}, extra={extra_batches}"
                        )

                    for idx, day_idx in enumerate(mon_thu_days):
                        day_batches = batches_per_day + (1 if idx < extra_batches else 0)
                        day_qty = day_batches * min_batch
                        if day_qty > 0:
                            plan_by_day[day_idx][art] = day_qty

                # 2) ÐŸÑÑ‚Ð½Ð¸Ñ†Ð°: Ð³Ð¾Ñ‚Ð¾Ð²Ð¸Ð¼ Ð½Ð° ÑÐ»ÐµÐ´ÑƒÑŽÑ‰Ð¸Ð¹ Ð¿Ð¾Ð½ÐµÐ´ÐµÐ»ÑŒÐ½Ð¸Ðº.
                # Ð‘ÐµÑ€Ñ‘Ð¼ Ð¼Ð°ÐºÑÐ¸Ð¼ÑƒÐ¼(Ð·Ð°ÐºÐ°Ð·Ñ‹ ÑÐ»ÐµÐ´. ÐŸÐ½, Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð· ÑÐ»ÐµÐ´. ÐŸÐ½), Ð·Ð°Ñ‚ÐµÐ¼ +10%.
                # ÐŸÑ€Ð¾Ð³Ð½Ð¾Ð· ÑÐ»ÐµÐ´. ÐŸÐ½ Ð¾Ñ†ÐµÐ½Ð¸Ð²Ð°ÐµÐ¼ ÐºÐ°Ðº Ð´Ð½ÐµÐ²Ð½ÑƒÑŽ Ð´Ð¾Ð»ÑŽ Ð½ÐµÐ´ÐµÐ»ÑŒÐ½Ð¾Ð³Ð¾ Ð¿Ñ€Ð¾Ð³Ð½Ð¾Ð·Ð°.
                next_mon_orders = max(0.0, float(next_monday_orders.get(art, 0)))
                next_mon_forecast = max(0.0, float(forecast) / float(num_workdays or 1))
                friday_base = math.ceil(max(next_mon_orders, next_mon_forecast) * 1.10)

                # ÐœÐ¸Ð½Ð¸Ð¼Ð°Ð»ÑŒÐ½Ñ‹Ð¹ Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ðº â€” ÐºÐ°Ðº floor, Ð½Ðµ ÐºÐ°Ðº Ð¿Ñ€Ð¸Ð±Ð°Ð²ÐºÐ°.
                friday_qty = max(float(friday_base), float(min_stock))
                friday_qty = round_to_batch(friday_qty, art)
                if friday_qty > 0:
                    plan_by_day[4][art] = plan_by_day[4].get(art, 0) + friday_qty

                # Ð•ÑÐ»Ð¸ Ð¸ Ð¾Ð±Ñ‹Ñ‡Ð½Ð¾Ð³Ð¾ Ð¾Ð±ÑŠÑ‘Ð¼Ð°, Ð¸ Ð¿ÑÑ‚Ð½Ð¸Ñ‡Ð½Ð¾Ð³Ð¾ Ð½ÐµÑ‚ â€” Ð¿Ñ€Ð¾Ð¿ÑƒÑÐºÐ°ÐµÐ¼.
                if regular_weekly_qty <= 0 and friday_qty <= 0:
                    continue
            else:
                if weekly_to_produce <= 0:
                    continue  # ÐÐ° ÑÐºÐ»Ð°Ð´Ðµ Ð´Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾!

                # ÐžÐºÑ€ÑƒÐ³Ð»ÑÐµÐ¼ Ð´Ð¾ Ñ€Ð°Ð·Ð¼ÐµÑ€Ð° Ð¿Ð°Ñ€Ñ‚Ð¸Ð¸
                weekly_to_produce = round_to_batch(weekly_to_produce, art)

                if weekly_to_produce <= 0:
                    continue

                # Ð Ð°Ð²Ð½Ð¾Ð¼ÐµÑ€Ð½Ð¾Ðµ Ñ€Ð°ÑÐ¿Ñ€ÐµÐ´ÐµÐ»ÐµÐ½Ð¸Ðµ Ð¿Ð¾ Ñ€Ð°Ð±Ð¾Ñ‡Ð¸Ð¼ Ð´Ð½ÑÐ¼
                total_batches = math.ceil(weekly_to_produce / min_batch) if min_batch > 0 else 1
                batches_per_day = total_batches // num_workdays
                extra_batches = total_batches % num_workdays

                # Ð›Ð¾Ð³Ð¸Ñ€ÑƒÐµÐ¼ Ð¿ÐµÑ€Ð²Ñ‹Ðµ Ð½ÐµÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Ð´Ð»Ñ Ð´Ð¸Ð°Ð³Ð½Ð¾ÑÑ‚Ð¸ÐºÐ¸
                if art in list(all_articles)[:3]:
                    logger.info(f"[PLAN] Art {art}: weekly={weekly_to_produce}, batches={total_batches}, per_day={batches_per_day}, extra={extra_batches}")

                for idx, day_idx in enumerate(enabled_days):
                    day_batches = batches_per_day
                    if idx < extra_batches:
                        day_batches += 1
                    day_qty = day_batches * min_batch
                    if day_qty > 0:
                        plan_by_day[day_idx][art] = day_qty

        # 5. Ð—ÐÐ“ÐžÐ¢ÐžÐ’ÐšÐ˜ (Prep Matrix) + SMART PULL
        prep_matrix = {}
    
        # Ð’ÑÐ¿Ð¾Ð¼Ð¾Ð³Ð°Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ðµ Ñ„ÑƒÐ½ÐºÑ†Ð¸Ð¸ Ð´Ð»Ñ prep_matrix
        def add_to_prep(comp_id, day_idx, amount):
            if comp_id not in components_db: return
            c_data = components_db[comp_id]
            c_name = c_data['name']
            if c_name not in prep_matrix:
                prep_matrix[c_name] = {
                    'id': comp_id, 'unit': c_data.get('unit', ''),
                    'batch_size': float(c_data.get('batch_size') or 1.0),
                    'total_batches': 0, 'total_amount': 0.0,
                    'days': {i: {'amount': 0.0, 'batches_ceil': 0} for i in range(7)}
                }
            prep_matrix[c_name]['days'][day_idx]['amount'] += amount

        def find_comp_id(name):
            for did, v in components_db.items():
                if v['name'] == name: return did
            clean = str(name).lower().replace(" ", "").replace("-", "")
            return comp_name_lookup.get(clean)

        # Ð—Ð°Ð¿Ð¾Ð»Ð½ÑÐµÐ¼ Ð¿Ð¾Ñ‚Ñ€ÐµÐ±Ð½Ð¾ÑÑ‚ÑŒ Ð² ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ð°Ñ…
        for day_idx in range(7):
            for art_nr, qty in plan_by_day[day_idx].items():
                rec = recipes.get(art_nr)
                if not rec: continue
                # Ð¢ÐµÑÑ‚Ð¾
                dough_id = rec.get('dough_id')
                if dough_id and dough_id in components_db:
                    ipt = float(rec.get('items_per_tray') or 1.0)
                    if ipt <= 0: ipt = 1.0
                    add_to_prep(dough_id, day_idx, qty / ipt)
                # Ð¡Ð¾ÑÑ‚Ð°Ð²
                if rec.get('composition'):
                    try:
                        for c in json.loads(rec['composition']):
                            c_name = c.get('component')
                            c_qty = float(c.get('quantity', 0))
                            fid = find_comp_id(c_name)
                            if fid: add_to_prep(fid, day_idx, qty * c_qty)
                    except: pass

        # Ð Ð°ÑÑ‡ÐµÑ‚ Ð¿Ð°Ñ€Ñ‚Ð¸Ð¹ (Chargen)
        for c_name, data in prep_matrix.items():
            bs = data['batch_size']
            grand_batches = 0
            grand_amount = 0.0
        
            for day_idx in range(7):
                amt = data['days'][day_idx]['amount']
                if amt > 0:
                    batches = math.ceil(amt / bs)
                    data['days'][day_idx]['batches_ceil'] = batches
                    grand_batches += batches
                
                    disp = round(amt, 1) if data['unit'] in ['Ð»Ð¸ÑÑ‚', 'ÑˆÑ‚'] else int(amt)
                    data['days'][day_idx]['amount'] = disp
                    grand_amount += disp
        
            data['total_batches'] = grand_batches
            data['total_amount'] = grand_amount

        # 6. ÐÐÐ“Ð Ð£Ð—ÐšÐ
        resource_load_weekly = {}
        # Ð¢Ð¾Ñ€Ñ‚Ñ‹
        for day_idx in range(7):
            for art, qty in plan_by_day[day_idx].items():
                if art in extra_resources:
                    for rid, t in extra_resources[art].items():
                        if rid in resources_map:
                            rn = resources_map[rid]['resource_name']
                            resource_load_weekly[rn] = resource_load_weekly.get(rn, 0) + (qty * t)
        # Ð¢ÐµÑÑ‚Ð¾
        for comp_name, data in prep_matrix.items():
            comp_id = data.get('id')
            batches = data.get('total_batches', 0)
            if batches > 0 and comp_id in components_db:
                info = components_db[comp_id]
                time_b = float(info.get('production_time_min') or 0.0)
                try: res_id = int(info.get('resource_id'))
                except: res_id = 0
                if time_b > 0 and res_id in resources_map:
                    rn = resources_map[res_id]['resource_name']
                    resource_load_weekly[rn] = resource_load_weekly.get(rn, 0) + (batches * time_b)

        # 7. ÐŸÐžÐ”Ð“ÐžÐ¢ÐžÐ’ÐšÐ Ð¡Ð¢Ð Ð£ÐšÐ¢Ð£Ð Ð« Ð”Ð›Ð¯ ÐžÐ¢Ð’Ð•Ð¢Ð
        # Ð¡Ð¿Ð¸ÑÐ¾Ðº Ñ‚Ð¾Ñ€Ñ‚Ð¾Ð²
        weekly_plan_list = []
        day_keys = ['mo', 'di', 'mi', 'do', 'fr', 'sa', 'so']
    
        for art in all_articles:
            # Ð¤Ð˜Ð›Ð¬Ð¢Ð : ÐŸÑ€Ð¾Ð¿ÑƒÑÐºÐ°ÐµÐ¼ Ñ‚Ð¾Ð²Ð°Ñ€Ñ‹ ÐºÐ¾Ñ‚Ð¾Ñ€Ñ‹Ñ… Ð½ÐµÑ‚ Ð² Ð±Ð°Ð·Ðµ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð²
            if art not in recipes:
                continue

            rec = recipes[art]
            name = rec.get('name', '')
            if not name or name == 'Unknown':
                continue  # ÐŸÑ€Ð¾Ð¿ÑƒÑÐºÐ°ÐµÐ¼ Ñ‚Ð¾Ð²Ð°Ñ€Ñ‹ Ð±ÐµÐ· Ð½Ð°Ð·Ð²Ð°Ð½Ð¸Ñ

            row = {
                'article_nr': art, 'name': name,
                'category': rec.get('category', 'Sonstiges'),
                'forecast': int(weekly_forecast.get(art, 0)),
                'orders': int(weekly_orders_total.get(art, 0) + (next_monday_orders.get(art, 0) if is_five_day_mode else 0)),
                'rest_kw': int(current_stock.get(art, 0)),
                'vorb_kw': 0, 'total_kw': 0, 'woche': week_start.isocalendar()[1]
            }
            for i in range(7):
                q = plan_by_day[i].get(art, 0)
                row[day_keys[i]] = int(q)
                row['total_kw'] += int(q)

            # ÐŸÐ¾ÐºÐ°Ð·Ñ‹Ð²Ð°ÐµÐ¼, ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ Ñ…Ð¾Ñ‚ÑŒ ÐºÐ°ÐºÐ¸Ðµ-Ñ‚Ð¾ Ñ†Ð¸Ñ„Ñ€Ñ‹
            weekly_plan_list.append(row)
    
        weekly_plan_list.sort(key=lambda x: x['name'])

        result = {
            'plan': weekly_plan_list,
            'prep_matrix': prep_matrix,
            'resource_load': resource_load_weekly,
            'week_start': week_start,
            'week_end': week_end,
            'resources_map': resources_map,
            'num_workdays': num_workdays
        }

        # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð² ÐºÑÑˆ (10 ÑÐµÐºÑƒÐ½Ð´)
        self._plan_cache[cache_key] = {'ts': time.time(), 'result': result}
        return result

    def _normalize_article_nr(self, value):
        raw = str(value or '').strip().replace(' ', '').replace(',', '')
        if '.' in raw and raw.replace('.', '').isdigit():
            raw = raw.split('.', 1)[0]
        return raw.zfill(5) if raw.isdigit() else raw

    def _get_recipe_active_map(self):
        """
        Карта активности по нормализованному артикулу.
        Если по одному артикулу есть конфликт active=1 и active=0, считаем неактивным.
        """
        states_by_article = {}
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT article_nr, COALESCE(active, 1) AS active FROM recipes")
            for row in cursor.fetchall():
                art = self._normalize_article_nr(row['article_nr'])
                if not art:
                    continue
                st = 1 if int(row['active'] or 0) == 1 else 0
                states_by_article.setdefault(art, set()).add(st)

        active_map = {}
        for art, states in states_by_article.items():
            active_map[art] = (1 in states) and (0 not in states)
        return active_map

    # ============================================================
    # ÐžÐ‘Ð ÐÐ‘ÐžÐ¢Ð§Ð˜Ðš ÐÐ•Ð”Ð•Ð›Ð¬ÐÐžÐ“Ðž ÐŸÐ›ÐÐÐ (Ð’Ñ‹Ð·Ñ‹Ð²Ð°ÐµÑ‚ ÑÐ´Ñ€Ð¾)
    # ============================================================
    async def handle_calculate_weekly_production_plan(self, ws, data):
        try:
            start_str = data.get('start_date')
            if not start_str: return
        
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            session = self.sessions.get_session(ws)
        
            # Ð’Ð«Ð—ÐžÐ’ Ð¯Ð”Ð Ð
            result = self._calculate_core_plan(start_date, session.user_id)
        
            # Ð¤Ð¾Ñ€Ð¼Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð¾Ñ‚Ð²ÐµÑ‚Ð° Ð´Ð»Ñ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°
            workshops_plan = {}
            for rid, r_data in result['resources_map'].items():
                res_name = r_data['resource_name']
                total_min = result['resource_load'].get(res_name, 0)
                daily_cap = r_data['quantity'] * r_data['shifts_count'] * r_data['shift_duration_min']
                weekly_cap = daily_cap * result['num_workdays']
            
                if weekly_cap > 0:
                    pct = (total_min / weekly_cap) * 100
                    workshops_plan[res_name] = f"{int(pct)}% ({int(total_min/60)}Ñ‡ / {int(weekly_cap/60)}Ñ‡)"
                else: workshops_plan[res_name] = "0% (0Ñ‡)"

            active_map = self._get_recipe_active_map()
            filtered_plan = [
                row for row in (result.get('plan', []) or [])
                if active_map.get(self._normalize_article_nr(row.get('article_nr', '')), False)
            ]

            msg = {
                'type': 'weekly_production_plan_data',
                'plan': filtered_plan,
                'prep_matrix': result['prep_matrix'],
                'workshops_plan': workshops_plan,
                'resource_load': result['resource_load'],
                'week_start': result['week_start'].strftime('%Y-%m-%d'),
                'week_end': result['week_end'].strftime('%Y-%m-%d'),
                'week_number': result['week_start'].isocalendar()[1]
            }
            await self.sessions.broadcast_to_all(msg)
        
        except Exception as e:
            logger.error(f"Weekly handler error: {e}")
            import traceback; traceback.print_exc()

    # ============================================================
    # ÐžÐ‘Ð ÐÐ‘ÐžÐ¢Ð§Ð˜Ðš Ð”ÐÐ•Ð’ÐÐžÐ“Ðž ÐŸÐ›ÐÐÐ (Ð’Ñ‹Ð·Ñ‹Ð²Ð°ÐµÑ‚ ÑÐ´Ñ€Ð¾ Ð¸ Ñ„Ð¸Ð»ÑŒÑ‚Ñ€ÑƒÐµÑ‚)
    # ============================================================
    async def handle_calculate_production_plan(self, ws, data):
        """
        Ð”ÐÐ•Ð’ÐÐžÐ™ ÐŸÐ›ÐÐ (FINAL):
        1. Ð’Ñ‹Ð·Ñ‹Ð²Ð°ÐµÑ‚ Ð•Ð´Ð¸Ð½Ð¾Ðµ Ð¯Ð´Ñ€Ð¾ (Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ñ†Ð¸Ñ„Ñ€Ñ‹ Ñ‚Ð¾Ñ€Ñ‚Ð¾Ð² ÑÐ¾Ð²Ð¿Ð°Ð´Ð°Ð»Ð¸ Ñ Ð½ÐµÐ´ÐµÐ»ÑŒÐ½Ñ‹Ð¼).
        2. Ð¤Ð¸Ð»ÑŒÑ‚Ñ€ÑƒÐµÑ‚ Ñ‚Ð¾Ñ€Ñ‚Ñ‹ Ð¸ Ð·Ð°Ð³Ð¾Ñ‚Ð¾Ð²ÐºÐ¸ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð½Ð° Ð­Ð¢ÐžÐ¢ Ð´ÐµÐ½ÑŒ.
        3. Ð ÐÐ¡Ð¡Ð§Ð˜Ð¢Ð«Ð’ÐÐ•Ð¢ Ð Ð•Ð¡Ð£Ð Ð¡Ð« Ð·Ð°Ð½Ð¾Ð²Ð¾, Ð½Ð¾ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð´Ð»Ñ Ð¾Ð±ÑŠÐµÐ¼Ð° ÑÑ‚Ð¾Ð³Ð¾ Ð´Ð½Ñ.
        """
        try:
            d_str = data.get('date')
            if not d_str: return
        
            target_date = datetime.strptime(d_str, "%Y-%m-%d").date()
            session = self.sessions.get_session(ws)
        
            # 1. Ð’Ð«Ð—ÐžÐ’ Ð¯Ð”Ð Ð
            result = self._calculate_core_plan(target_date, session.user_id)
        
            # ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ Ð¸Ð½Ð´ÐµÐºÑ Ð´Ð½Ñ (0=ÐŸÐ½...6=Ð’Ñ)
            day_idx = (target_date - result['week_start']).days
            day_keys = ['mo', 'di', 'mi', 'do', 'fr', 'sa', 'so']
            day_key = day_keys[day_idx] if 0 <= day_idx <= 6 else None
        
            if day_idx < 0 or day_idx > 6:
                await websocket.send(json.dumps({'type': 'error', 'message': 'Ð”Ð°Ñ‚Ð° Ð²Ð½Ðµ Ñ‚ÐµÐºÑƒÑ‰ÐµÐ¹ Ð½ÐµÐ´ÐµÐ»Ð¸'}))
                return

            # --- ÐŸÐžÐ”Ð“Ð Ð£Ð—ÐšÐ Ð”ÐÐÐÐ«Ð¥ Ð”Ð›Ð¯ Ð ÐÐ¡Ð§Ð•Ð¢Ð Ð Ð•Ð¡Ð£Ð Ð¡ÐžÐ’ ---
            # ÐÐ°Ð¼ Ð½ÑƒÐ¶Ð½Ñ‹ ÑÐ¿Ñ€Ð°Ð²Ð¾Ñ‡Ð½Ð¸ÐºÐ¸, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð¿Ð¾ÑÑ‡Ð¸Ñ‚Ð°Ñ‚ÑŒ Ð²Ñ€ÐµÐ¼Ñ
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # Ð ÐµÑÑƒÑ€ÑÑ‹
                cursor.execute("SELECT resource_id, resource_name, quantity, shifts_count, shift_duration_min FROM factory_resources")
                resources_map = {int(r['resource_id']): dict(r) for r in cursor.fetchall()}
            
                # ÐšÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ñ‹ (Ð²Ñ€ÐµÐ¼Ñ Ð½Ð° Ð¿Ð°Ñ€Ñ‚Ð¸ÑŽ)
                cursor.execute("SELECT dough_id, production_time_min, resource_id FROM dough_types")
                components_db = {row['dough_id']: dict(row) for row in cursor.fetchall()}
            
                # Ð”Ð¾Ð¿. Ñ€ÐµÑÑƒÑ€ÑÑ‹ (ÑÐ±Ð¾Ñ€ÐºÐ°)
                extra_resources = {}
                try:
                    cursor.execute("SELECT article_nr, resource_id, time_needed_min FROM product_resource_consumption")
                    for row in cursor.fetchall():
                        an = str(row['article_nr']).strip().zfill(5)
                        rid = int(row['resource_id'])
                        if an not in extra_resources: extra_resources[an] = {}
                        extra_resources[an][rid] = float(row['time_needed_min'])
                except: pass

            # 2. Ð¡ÐŸÐ ÐžÐ¡ ÐÐ Ð”Ð•ÐÐ¬ (Ð·Ð°ÐºÐ°Ð·Ñ‹ Ñ Ð´Ð°Ñ‚Ð¾Ð¹ Ð´Ð¾ÑÑ‚Ð°Ð²ÐºÐ¸ = target_date)
            daily_orders = {}
            all_orders = self.db.get_all_orders()
            for order in all_orders:
                d_str = order.get('delivery_date')
                if not d_str:
                    continue
                try:
                    d_date = datetime.strptime(d_str, "%Y-%m-%d").date()
                except:
                    continue
                if d_date != target_date:
                    continue
                for art in order.get('artikel', []):
                    an = str(art.get('artikel_nr') or art.get('nummer', '')).strip().zfill(5)
                    qty = float(art.get('menge', 0))
                    if qty > 0:
                        daily_orders[an] = daily_orders.get(an, 0) + qty

            active_map = self._get_recipe_active_map()

            # 3. Ð¤Ð¸Ð»ÑŒÑ‚Ñ€ÑƒÐµÐ¼ Ð¢ÐžÐ Ð¢Ð« Ð¸ ÑÑ‡Ð¸Ñ‚Ð°ÐµÐ¼ Ð½Ð°Ð³Ñ€ÑƒÐ·ÐºÑƒ Ð¡Ð‘ÐžÐ ÐšÐ˜
            daily_plan_items = []
            daily_resource_load = {} # {ResName: minutes}

            for row in result['plan']:
                qty_today = row.get(day_key, 0)
                art_nr = row['article_nr']
                if not active_map.get(self._normalize_article_nr(art_nr), False):
                    continue
                demand_today = int(daily_orders.get(art_nr, 0))

                # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ
                daily_plan_items.append({
                    'article_nr': art_nr,
                    'name': row['name'],
                    'category': row.get('category', 'Sonstiges'), # <--- Ð˜Ð¡ÐŸÐ ÐÐ’Ð›Ð•ÐÐ˜Ð•: Ð‘ÐµÑ€ÐµÐ¼ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸ÑŽ Ð¸Ð· row
                    'forecast': int(row['forecast'] / result['num_workdays']),
                    'available_stock': row['rest_kw'],
                    'net_demand': demand_today,
                    'quantity': qty_today,
                    'surplus': 0,
                    'dough_name': '', # ÐœÐ¾Ð¶Ð½Ð¾ Ð´Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ
                    'batches': 0      # ÐœÐ¾Ð¶Ð½Ð¾ Ð´Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ
                })
            
                # Ð¡Ñ‡Ð¸Ñ‚Ð°ÐµÐ¼ Ñ€ÐµÑÑƒÑ€ÑÑ‹ Ð¡Ð‘ÐžÐ ÐšÐ˜ (Ð“Ñ€ÑƒÐ½Ñ‚Ð¾Ð²ÐºÐ°, Ð”ÐµÐºÐ¾Ñ€...)
                if qty_today > 0 and row['article_nr'] in extra_resources:
                    for rid, t in extra_resources[row['article_nr']].items():
                        if rid in resources_map:
                            rn = resources_map[rid]['resource_name']
                            daily_resource_load[rn] = daily_resource_load.get(rn, 0) + (qty_today * t)
        
            # 3. Ð¤Ð¸Ð»ÑŒÑ‚Ñ€ÑƒÐµÐ¼ Ð—ÐÐ“ÐžÐ¢ÐžÐ’ÐšÐ˜ Ð¸ ÑÑ‡Ð¸Ñ‚Ð°ÐµÐ¼ Ð½Ð°Ð³Ñ€ÑƒÐ·ÐºÑƒ ÐŸÐ•Ð§Ð˜
            daily_components = []
            prep = result['prep_matrix']
        
            for c_name, c_data in prep.items():
                day_data = c_data['days'].get(day_idx, {})
                qty = day_data.get('amount', 0)
                batches = day_data.get('batches_ceil', 0)
            
                if qty > 0:
                    daily_components.append({
                        'name': c_name,
                        'type': 'ÐšÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚',
                        'qty_needed': qty,
                        'unit': c_data['unit'],
                        'batches': batches
                    })
                
                    # Ð¡Ñ‡Ð¸Ñ‚Ð°ÐµÐ¼ Ñ€ÐµÑÑƒÑ€ÑÑ‹ Ð’Ð«ÐŸÐ•Ð§ÐšÐ˜/Ð’ÐÐ ÐšÐ˜
                    comp_id = c_data['id']
                    if batches > 0 and comp_id in components_db:
                        info = components_db[comp_id]
                        time_batch = float(info.get('production_time_min') or 0.0)
                        try: res_id = int(info.get('resource_id') or 0)
                        except: res_id = 0
                    
                        if time_batch > 0 and res_id > 0 and res_id in resources_map:
                            rn = resources_map[res_id]['resource_name']
                            daily_resource_load[rn] = daily_resource_load.get(rn, 0) + (batches * time_batch)

            # 4. Ð¤ÐžÐ ÐœÐ˜Ð Ð£Ð•Ðœ Ð¡ÐŸÐ˜Ð¡ÐžÐš Ð Ð•Ð¡Ð£Ð Ð¡ÐžÐ’ Ð¡Ðž Ð¡Ð¢ÐÐ¢Ð£Ð¡ÐÐœÐ˜
            res_list = []
            for rid, r_data in resources_map.items():
                r_name = r_data['resource_name']
                plan_min = daily_resource_load.get(r_name, 0)
            
                # Ð”ÐÐ•Ð’ÐÐžÐ™ Ð›Ð˜ÐœÐ˜Ð¢ (Ð½Ðµ ÑƒÐ¼Ð½Ð¾Ð¶Ð°ÐµÐ¼ Ð½Ð° Ð½ÐµÐ´ÐµÐ»ÑŽ!)
                limit_min = r_data['quantity'] * r_data['shifts_count'] * r_data['shift_duration_min']
            
                pct = (plan_min / limit_min * 100) if limit_min > 0 else 0
            
                status = 'normal'
                if pct > 100: status = 'overload'
                elif pct > 80: status = 'warning'
            
                res_list.append({
                    'resource_name': r_name,
                    'planned_load_min': int(plan_min),
                    'available_capacity_min': int(limit_min),
                    'utilization_percent': round(pct, 1),
                    'status': status,
                    'status_label': f"{int(pct)}%"
                })

            msg = {
                'type': 'production_plan_data',
                'plan': sorted(daily_plan_items, key=lambda x: x['name']),
                'totals': {'cakes': sum(x['quantity'] for x in daily_plan_items)},
                'components_plan': sorted(daily_components, key=lambda x: x['name']),
                'resource_load': sorted(res_list, key=lambda x: x['utilization_percent'], reverse=True),
                'bottlenecks': [],
                'recommendations': [],
                'stock_info': {}
            }
            await self.sessions.broadcast_to_all(msg)
        
        except Exception as e:
            logger.error(f"Daily handler error: {e}")
            import traceback; traceback.print_exc()
    
    async def handle_get_daily_shipping_summary(self, websocket, data):
        """
        Ð¡Ð²Ð¾Ð´Ð½Ð°Ñ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¾Ñ‚Ð³Ñ€ÑƒÐ·Ð¾Ðº Ð½Ð° Ð´ÐµÐ½ÑŒ.
        ÐŸÐ¾ÐºÐ°Ð·Ñ‹Ð²Ð°ÐµÑ‚ Ñ‡Ñ‚Ð¾ Ð½ÑƒÐ¶Ð½Ð¾ Ð¾Ñ‚Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ Ð½Ð° ÑƒÐºÐ°Ð·Ð°Ð½Ð½ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ (Ð¸Ð· Ð·Ð°ÐºÐ°Ð·Ð¾Ð²).
        """
        try:
            date_str = data.get('date')
            if not date_str:
                return

            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð²ÑÐµ Ð·Ð°ÐºÐ°Ð·Ñ‹
            all_orders = self.db.get_all_orders()

            # Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ñ‹ Ð´Ð»Ñ Ð½Ð°Ð·Ð²Ð°Ð½Ð¸Ð¹
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT article_nr, name, category, min_stock_level, COALESCE(active, 1) AS active FROM recipes")
                recipe_info = {}
                recipe_states = {}
                for row in cursor.fetchall():
                    art = self._normalize_article_nr(row['article_nr'])
                    recipe_info[art] = {
                        'name': row['name'],
                        'category': row['category'] or '',
                        'min_stock': float(row['min_stock_level'] or 0)
                    }
                    recipe_states.setdefault(art, set()).add(1 if int(row['active'] or 0) == 1 else 0)
                recipe_active_map = {art: ((1 in st) and (0 not in st)) for art, st in recipe_states.items()}

            # ÐŸÑ€Ð°Ð²Ð¸Ð»Ð¾ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¾Ð²:
            # - Ð±ÑƒÐ´ÑƒÑ‰Ð¸Ðµ Ð´Ð°Ñ‚Ñ‹ ÑÐ²Ð¾Ð´Ð½Ð¾Ð¹: Ð±ÐµÑ€Ñ‘Ð¼ Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ðµ Ð°ÐºÑ‚ÑƒÐ°Ð»ÑŒÐ½Ñ‹Ðµ Ð²Ð²ÐµÐ´Ñ‘Ð½Ð½Ñ‹Ðµ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸
            # - ÑÐµÐ³Ð¾Ð´Ð½Ñ Ð¸ Ð¿Ñ€Ð¾ÑˆÐ»Ñ‹Ðµ Ð´Ð°Ñ‚Ñ‹: Ð±ÐµÑ€Ñ‘Ð¼ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸ Ð¸Ð¼ÐµÐ½Ð½Ð¾ Ð½Ð° ÑÑ‚Ñƒ Ð´Ð°Ñ‚Ñƒ
            latest_stock_date = self.db.get_latest_stock_report_date()
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                today = datetime.now().date()
            except Exception:
                target_date = None
                today = datetime.now().date()

            if target_date and target_date > today:
                stock_date_to_use = latest_stock_date
            else:
                stock_date_to_use = date_str

            stock_report = self.db.get_daily_stock_report(stock_date_to_use) if stock_date_to_use else []
            stock_by_article = {}
            for stock_row in stock_report:
                art_nr = str(stock_row.get('article_nr', '')).strip().zfill(5)
                stock_by_article[art_nr] = float(stock_row.get('quantity') or 0)

            shipping_summary = {}

            for order in all_orders:
                delivery_date = order.get('delivery_date', '')
                if delivery_date != date_str:
                    continue

                for art in order.get('artikel', []):
                    art_nr = self._normalize_article_nr(art.get('artikel_nr') or art.get('nummer', ''))
                    if not recipe_active_map.get(art_nr, False):
                        continue
                    qty = float(art.get('menge', 0))
                    if qty > 0:
                        if art_nr not in shipping_summary:
                            rec = recipe_info.get(art_nr, {})
                            shipping_summary[art_nr] = {
                                'article_nr': art_nr,
                                'name': rec.get('name', art.get('name', 'Unknown')),
                                'category': rec.get('category', ''),
                                'quantity': 0,
                                'stock': 0,
                                'difference': 0,
                                'coverage_percent': 0.0,
                                'min_stock': rec.get('min_stock', 0.0)
                            }
                        shipping_summary[art_nr]['quantity'] += qty

            # ÐŸÑ€ÐµÐ¾Ð±Ñ€Ð°Ð·ÑƒÐµÐ¼ Ð² ÑÐ¿Ð¸ÑÐ¾Ðº Ð¸ ÑÐ¾Ñ€Ñ‚Ð¸Ñ€ÑƒÐµÐ¼ Ð¿Ð¾ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñƒ
            summary_list = list(shipping_summary.values())
            for item in summary_list:
                stock_val = float(stock_by_article.get(item['article_nr'], 0))
                item['stock'] = stock_val
                item['difference'] = stock_val - float(item['quantity'])
                qty = float(item.get('quantity') or 0)
                item['coverage_percent'] = round((stock_val / qty) * 100, 1) if qty > 0 else 0.0
            summary_list.sort(key=lambda x: x['article_nr'])

            # Ð˜Ñ‚Ð¾Ð³Ð¾
            total_qty = sum(item['quantity'] for item in summary_list)
            total_stock = sum(item.get('stock', 0) for item in summary_list)
            total_diff = sum(item.get('difference', 0) for item in summary_list)

            await websocket.send(json.dumps({
                'type': 'daily_shipping_summary',
                'date': date_str,
                'stock_date_used': stock_date_to_use,
                'items': summary_list,
                'total_items': len(summary_list),
                'total_quantity': int(total_qty),
                'total_stock': int(total_stock),
                'total_difference': int(total_diff)
            }))

            logger.info(
                f"Daily shipping summary for {date_str}: {len(summary_list)} items, {int(total_qty)} units, "
                f"stock source={stock_date_to_use or 'none'}"
            )

        except Exception as e:
            logger.error(f"Error getting daily shipping summary: {e}")
            import traceback
            traceback.print_exc()

    async def handle_update_production_fact(self, websocket, data):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÑ‚ Ñ„Ð°ÐºÑ‚ Ð¸ Ð“ÐžÐ’ÐžÐ Ð˜Ð¢ ÐšÐ›Ð˜Ð•ÐÐ¢Ð£ Ð¾Ð±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ"""
        date_str = data.get('date')
        article_nr = str(data.get('article_nr')).strip().zfill(5)
        fact_qty = float(data.get('fact_qty', 0))

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO production_facts (date, article_nr, fact_qty)
                VALUES (?, ?, ?)
                ON CONFLICT(date, article_nr) DO UPDATE SET fact_qty = excluded.fact_qty
            ''', (date_str, article_nr, fact_qty))
            conn.commit()

            # ÐšÐ Ð˜Ð¢Ð˜Ð§ÐÐž: ÐŸÐµÑ€ÐµÑÑ‡Ð¸Ñ‚Ñ‹Ð²Ð°ÐµÐ¼ Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ðº Ð½Ð° Ð­Ð¢ÐžÐ¢ Ð”Ð•ÐÐ¬ Ñ ÑƒÑ‡ÐµÑ‚Ð¾Ð¼ Ñ„Ð°ÐºÑ‚Ð°!
            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ ÑÐºÐ¾Ð»ÑŒÐºÐ¾ Ð½ÑƒÐ¶Ð½Ð¾ Ð±Ñ‹Ð»Ð¾ Ð¿Ñ€Ð¾Ð¸Ð·Ð²ÐµÑÑ‚Ð¸
            cursor.execute('''
                SELECT SUM(artikel_qty)
                FROM (
                    SELECT json_extract(artikel.value, '$.menge') as artikel_qty
                    FROM orders,
                    json_each(json_extract(order_data, '$.artikel')) as artikel
                    WHERE production_date = ?
                    AND (json_extract(artikel.value, '$.artikel_nr') = ?
                    OR json_extract(artikel.value, '$.nummer') = ?)
                )
            ''', (date_str, article_nr, article_nr))
            needed_row = cursor.fetchone()
            needed_qty = float(needed_row[0]) if needed_row and needed_row[0] else 0.0

            conn.close()

            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ðº Ñ Ð¿Ñ€ÐµÐ´Ñ‹Ð´ÑƒÑ‰ÐµÐ³Ð¾ Ð´Ð½Ñ
            prev_date = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
            prev_stock = self.stock_manager.get_stock(prev_date, article_nr)

            # ÐŸÐµÑ€ÐµÑÑ‡Ð¸Ñ‚Ñ‹Ð²Ð°ÐµÐ¼ Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ðº: Ð‘Ñ‹Ð»Ð¾ + Ð¤Ð°ÐºÑ‚ - ÐÑƒÐ¶Ð½Ð¾
            new_surplus = int(round(prev_stock + fact_qty - needed_qty))
            self.stock_manager.set_stock(date_str, article_nr, max(0, new_surplus))

            logger.info(f"âœ… Ð¤Ð°ÐºÑ‚ ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½: {article_nr} Ð½Ð° {date_str}: {fact_qty} ÑˆÑ‚, Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ðº Ð¿ÐµÑ€ÐµÑÑ‡Ð¸Ñ‚Ð°Ð½: {new_surplus}")

            # Ð’ÐÐ–ÐÐž: ÐŸÐ¾ÑÐ»Ðµ ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ Ð²Ñ‹Ð·Ñ‹Ð²Ð°ÐµÐ¼ Ñ€Ð°ÑÑ‡ÐµÑ‚ Ð¿Ð»Ð°Ð½Ð° Ð´Ð»Ñ ÑÑ‚Ð¾Ð¹ Ð¶Ðµ Ð´Ð°Ñ‚Ñ‹
            # Ð­Ñ‚Ð¾ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ 'production_plan_data' Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚ ÑÐ°Ð¼ Ð¿ÐµÑ€ÐµÑ€Ð¸ÑÑƒÐµÑ‚ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ
            await self.handle_calculate_production_plan(websocket, {'date': date_str})
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ Ñ„Ð°ÐºÑ‚Ð°: {e}")

    async def handle_adjust_stock(self, websocket, data):
        """
        Ð Ð£Ð§ÐÐžÐ™ Ð’Ð’ÐžÐ” Ð—ÐÐŸÐÐ¡Ð (ÐÐ´Ð¼Ð¸Ð½Ð¾Ð¼).
        Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÑ‚ ÑÑ‚Ð¾ ÐºÐ°Ðº Ð˜Ð½Ð²ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð·Ð°Ñ†Ð¸ÑŽ Ð½Ð° Ð’Ð§Ð•Ð ÐÐ¨ÐÐ˜Ð™ Ð²ÐµÑ‡ÐµÑ€.
        """
        try:
            # Ð”Ð°Ñ‚Ð° Ð¿Ð»Ð°Ð½Ð° (Ð¡ÐµÐ³Ð¾Ð´Ð½Ñ)
            plan_date_str = data.get('date')
            article_nr = str(data.get('article_nr')).strip().zfill(5)
            new_qty = float(data.get('new_qty', 0))
        
            # Ð’Ñ‹Ñ‡Ð¸ÑÐ»ÑÐµÐ¼ Ð´Ð°Ñ‚Ñƒ Ð¾Ñ‚Ñ‡ÐµÑ‚Ð° (Ð’Ñ‡ÐµÑ€Ð°)
            plan_date = datetime.strptime(plan_date_str, '%Y-%m-%d')
            report_date = plan_date - timedelta(days=1)
            report_date_str = report_date.strftime('%Y-%m-%d')
        
            session = self.sessions.get_session(websocket)
            username = session.username if session else "Admin"

            # ÐŸÐ˜Ð¨Ð•Ðœ Ð’ Ð¢ÐÐ‘Ð›Ð˜Ð¦Ð£ ÐžÐ¢Ð§Ð•Ð¢ÐžÐ’ (daily_stock_reports)
            # Ð­Ñ‚Ð¾ ÑÐ²ÑÐ·Ñ‹Ð²Ð°ÐµÑ‚ Ñ€ÑƒÑ‡Ð½Ð¾Ð¹ Ð²Ð²Ð¾Ð´ Ñ ÑÐ¸ÑÑ‚ÐµÐ¼Ð¾Ð¹ Ð¸Ð½Ð²ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð·Ð°Ñ†Ð¸Ð¸
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ðº
            cursor.execute('''
                INSERT INTO daily_stock_reports (date, article_nr, quantity, last_editor, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(date, article_nr) DO UPDATE SET
                quantity = excluded.quantity,
                last_editor = excluded.last_editor,
                updated_at = excluded.updated_at
            ''', (report_date_str, article_nr, new_qty, username, datetime.now().isoformat()))

            # ============================================================
            # ÐÐ’Ð¢ÐžÐ¤Ð˜ÐšÐ¡ÐÐ¦Ð˜Ð¯ ÐŸÐ ÐžÐ¨Ð•Ð”Ð¨Ð˜Ð¥ Ð”ÐÐ•Ð™
            # ÐŸÑ€Ð¸Ð½Ñ†Ð¸Ð¿: Ð¿Ñ€Ð¾ÑˆÐµÐ´ÑˆÐ¸Ðµ Ð´Ð½Ð¸ (Ð¾Ñ‚ Ð½Ð°Ñ‡Ð°Ð»Ð° Ð½ÐµÐ´ÐµÐ»Ð¸ Ð´Ð¾ report_date) Ñ„Ð¸ÐºÑÐ¸Ñ€ÑƒÑŽÑ‚ÑÑ
            # Ð¤Ð¾Ñ€Ð¼ÑƒÐ»Ð°: Ð¤Ð°ÐºÑ‚ = ÐžÑÑ‚Ð°Ñ‚Ð¾Ðº_ÑÐµÐ³Ð¾Ð´Ð½Ñ - ÐžÑÑ‚Ð°Ñ‚Ð¾Ðº_Ð²Ñ‡ÐµÑ€Ð° + ÐŸÑ€Ð¾Ð´Ð°Ð¶Ð¸
            # ============================================================
            week_start = plan_date.date() - timedelta(days=plan_date.weekday())

            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð²ÑÐµ Ð·Ð°ÐºÐ°Ð·Ñ‹ Ð´Ð»Ñ Ñ€Ð°ÑÑ‡Ñ‘Ñ‚Ð° Ð¿Ñ€Ð¾Ð´Ð°Ð¶
            all_orders = self.db.get_all_orders()

            # Ð¤Ð¸ÐºÑÐ¸Ñ€ÑƒÐµÐ¼ ÐºÐ°Ð¶Ð´Ñ‹Ð¹ Ð´ÐµÐ½ÑŒ Ð¾Ñ‚ Ð½Ð°Ñ‡Ð°Ð»Ð° Ð½ÐµÐ´ÐµÐ»Ð¸ Ð´Ð¾ report_date Ð²ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð¾
            current_day = week_start
            while current_day <= report_date.date():
                day_str = current_day.strftime('%Y-%m-%d')
                prev_day_str = (current_day - timedelta(days=1)).strftime('%Y-%m-%d')

                # ÐžÑÑ‚Ð°Ñ‚Ð¾Ðº Ð½Ð° ÐºÐ¾Ð½ÐµÑ† Ñ‚ÐµÐºÑƒÑ‰ÐµÐ³Ð¾ Ð´Ð½Ñ
                cursor.execute("""
                    SELECT quantity FROM daily_stock_reports
                    WHERE date = ? AND article_nr = ?
                """, (day_str, article_nr))
                row = cursor.fetchone()
                stock_today = float(row[0]) if row else 0

                # ÐžÑÑ‚Ð°Ñ‚Ð¾Ðº Ð½Ð° ÐºÐ¾Ð½ÐµÑ† Ð¿Ñ€ÐµÐ´Ñ‹Ð´ÑƒÑ‰ÐµÐ³Ð¾ Ð´Ð½Ñ
                cursor.execute("""
                    SELECT quantity FROM daily_stock_reports
                    WHERE date = ? AND article_nr = ?
                """, (prev_day_str, article_nr))
                row = cursor.fetchone()
                stock_yesterday = float(row[0]) if row else 0

                # ÐŸÑ€Ð¾Ð´Ð°Ð¶Ð¸ Ð·Ð° Ð´ÐµÐ½ÑŒ (ÑÑƒÐ¼Ð¼Ð° Ð¸Ð· Ð·Ð°ÐºÐ°Ð·Ð¾Ð² Ñ delivery_date = current_day)
                sales = 0
                for order in all_orders:
                    d_str = order.get('delivery_date')
                    if d_str == day_str:
                        for art in order.get('artikel', []):
                            an = str(art.get('artikel_nr') or art.get('nummer', '')).strip().zfill(5)
                            if an == article_nr:
                                sales += float(art.get('menge', 0))

                # Ð¤ÐžÐ ÐœÐ£Ð›Ð: Ð¤Ð°ÐºÑ‚ = ÐžÑÑ‚Ð°Ñ‚Ð¾Ðº_ÑÐµÐ³Ð¾Ð´Ð½Ñ - ÐžÑÑ‚Ð°Ñ‚Ð¾Ðº_Ð²Ñ‡ÐµÑ€Ð° + ÐŸÑ€Ð¾Ð´Ð°Ð¶Ð¸
                fact_qty = stock_today - stock_yesterday + sales
                fact_qty = max(0, fact_qty)  # ÐÐµ Ð¼Ð¾Ð¶ÐµÑ‚ Ð±Ñ‹Ñ‚ÑŒ Ð¾Ñ‚Ñ€Ð¸Ñ†Ð°Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ð¼

                # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð² locked_production_plan
                cursor.execute("""
                    INSERT OR REPLACE INTO locked_production_plan
                    (date, article_nr, locked_qty, locked_by, locked_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (day_str, article_nr, fact_qty, username, datetime.now().isoformat()))

                current_day += timedelta(days=1)

            conn.commit()
            conn.close()

            logger.info(f"âœ… ÐÐ´Ð¼Ð¸Ð½ Ð¾Ð±Ð½Ð¾Ð²Ð¸Ð» Ð·Ð°Ð¿Ð°Ñ: {article_nr} Ð½Ð° ÑƒÑ‚Ñ€Ð¾ {plan_date_str} = {new_qty}")
            logger.info(f"ðŸ”’ Ð—Ð°Ñ„Ð¸ÐºÑÐ¸Ñ€Ð¾Ð²Ð°Ð½Ñ‹ Ð´Ð½Ð¸ {week_start} - {report_date.date()} Ð´Ð»Ñ {article_nr}")

            # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ Ð¿Ð»Ð°Ð½ (Ñ‚ÐµÐ¿ÐµÑ€ÑŒ Ñ ÑƒÑ‡Ñ‘Ñ‚Ð¾Ð¼ Ñ„Ð¸ÐºÑÐ°Ñ†Ð¸Ð¸)
            await self.handle_calculate_production_plan(websocket, {'date': plan_date_str})
        
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð²Ð²Ð¾Ð´Ð° Ð·Ð°Ð¿Ð°ÑÐ°: {e}")

    async def handle_save_plan_settings(self, websocket, data, session):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¸ ÐžÐ‘ÐÐžÐ’Ð˜Ð¢Ð¬ Ð’Ð¡Ð•Ð¥"""
        workdays = data.get('workdays', [])
        visible_columns = data.get('visible_columns', [])
        user_id = session.user_id
    
        # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð´Ð°Ñ‚Ñƒ, ÐºÐ¾Ñ‚Ð¾Ñ€Ð°Ñ ÑÐµÐ¹Ñ‡Ð°Ñ Ð¾Ñ‚ÐºÑ€Ñ‹Ñ‚Ð° (ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ)
        current_date = data.get('current_date') 

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # 1. Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ñ€Ð°Ð±Ð¾Ñ‡Ð¸Ðµ Ð´Ð½Ð¸ (Ð“Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ð¾ Ð´Ð»Ñ Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð°)
            # Ð’ÐÐ–ÐÐž: Ð’ SQLite NULL != NULL Ð² PRIMARY KEY, Ð¿Ð¾ÑÑ‚Ð¾Ð¼Ñƒ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ DELETE + INSERT
            # Ð¡Ð½Ð°Ñ‡Ð°Ð»Ð° ÑƒÐ´Ð°Ð»ÑÐµÐ¼ ÑÑ‚Ð°Ñ€Ñ‹Ðµ Ð³Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ workdays
            cursor.execute("DELETE FROM plan_settings WHERE user_id IS NULL AND setting_key = 'workdays'")

            # Ð—Ð°Ñ‚ÐµÐ¼ Ð²ÑÑ‚Ð°Ð²Ð»ÑÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ðµ
            cursor.execute('''
                INSERT INTO plan_settings (user_id, setting_key, setting_value, updated_at)
                VALUES (NULL, 'workdays', ?, CURRENT_TIMESTAMP)
            ''', (json.dumps(workdays),))

            logger.info(f"[PLAN] Saved workdays to DB: {workdays}")

            # 2. ÐšÐ¾Ð»Ð¾Ð½ÐºÐ¸ (Ð»Ð¸Ñ‡Ð½Ñ‹Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸)
            cursor.execute('''
                INSERT INTO plan_settings (user_id, setting_key, setting_value)
                VALUES (?, 'visible_columns', ?)
                ON CONFLICT(user_id, setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, json.dumps(visible_columns)))

            conn.commit()
            conn.close()

            logger.info(f"âœ… ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¿Ð»Ð°Ð½Ð° Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ñ‹: {workdays}")

            # 3. Ð ÐÐ¡Ð¡Ð«Ð›ÐšÐ Ð’Ð¡Ð•Ðœ: ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¸Ð·Ð¼ÐµÐ½Ð¸Ð»Ð¸ÑÑŒ!
            # ÐœÑ‹ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ ÑÐ¿ÐµÑ†Ð¸Ð°Ð»ÑŒÐ½Ð¾Ðµ ÑÐ¾Ð±Ñ‹Ñ‚Ð¸Ðµ, Ñ‡Ñ‚Ð¾Ð±Ñ‹ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ñ‹ Ð¿ÐµÑ€ÐµÐ·Ð°Ð¿Ñ€Ð¾ÑÐ¸Ð»Ð¸ Ð¿Ð»Ð°Ð½
            await self.sessions.broadcast_to_all({
                'type': 'plan_settings_updated',
                'workdays': workdays
            })
        
            # Ð¢Ð°ÐºÐ¶Ðµ ÑˆÐ»ÐµÐ¼ Ð¿Ð¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð¸Ðµ Ñ‚Ð¾Ð¼Ñƒ, ÐºÑ‚Ð¾ ÑÐ¾Ñ…Ñ€Ð°Ð½Ð¸Ð»
            await websocket.send(json.dumps({'type': 'plan_settings_saved', 'success': True}))

        except Exception as e:
            logger.error(f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ° handle_save_plan_settings: {e}")

    async def handle_get_plan_settings(self, websocket, session):
        """Ð—Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¿Ð»Ð°Ð½Ð° Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð°"""
        user_id = session.user_id
        default_workdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
        default_visible_columns = ['workshop', 'article_nr', 'name', 'stock', 'demand', 'plan', 'fact', 'surplus', 'dough', 'batches']

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # ÐŸÐ¾Ð¿Ñ‹Ñ‚Ð°Ñ‚ÑŒÑÑ Ð·Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ
            cursor.execute('''
                SELECT setting_key, setting_value
                FROM plan_settings
                WHERE user_id = ?
            ''', (user_id,))

            settings = {}
            for row in cursor.fetchall():
                key = row[0]
                value = json.loads(row[1])
                settings[key] = value

            # ÐŸÐ¾Ð´Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ð³Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ ÐºÐ°Ðº fallback Ð´Ð»Ñ Ð¾Ñ‚ÑÑƒÑ‚ÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ñ… ÐºÐ»ÑŽÑ‡ÐµÐ¹.
            # Ð’Ð°Ð¶Ð½Ð¾: Ñƒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ Ð¼Ð¾Ð³ÑƒÑ‚ Ð±Ñ‹Ñ‚ÑŒ ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ñ‹ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ visible_columns,
            # Ñ‚Ð¾Ð³Ð´Ð° workdays Ð´Ð¾Ð»Ð¶Ð½Ñ‹ Ð¿Ñ€Ð¸Ñ…Ð¾Ð´Ð¸Ñ‚ÑŒ Ð¸Ð· Ð³Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ñ…, Ð° Ð½Ðµ Ð¿ÑƒÑÑ‚Ñ‹Ð¼Ð¸.
            if not settings or 'workdays' not in settings or 'visible_columns' not in settings:
                cursor.execute('''
                    SELECT setting_key, setting_value
                    FROM plan_settings
                    WHERE user_id IS NULL
                ''')

                for row in cursor.fetchall():
                    key = row[0]
                    value = json.loads(row[1])
                    if key not in settings:
                        settings[key] = value

            # Ð‘ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ñ‹Ðµ Ð´ÐµÑ„Ð¾Ð»Ñ‚Ñ‹, ÐµÑÐ»Ð¸ Ð² Ð‘Ð” ÐºÐ»ÑŽÑ‡ÐµÐ¹ Ð½ÐµÑ‚ Ð²Ð¾Ð¾Ð±Ñ‰Ðµ.
            if not settings.get('workdays'):
                settings['workdays'] = default_workdays.copy()
            if not settings.get('visible_columns'):
                settings['visible_columns'] = default_visible_columns.copy()

            conn.close()

            logger.info(f"ðŸ“¥ ÐÐ°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¿Ð»Ð°Ð½Ð° Ð·Ð°Ð³Ñ€ÑƒÐ¶ÐµÐ½Ñ‹ Ð´Ð»Ñ user_id={user_id}")

            await websocket.send(json.dumps({
                'type': 'plan_settings_data',
                'settings': settings
            }))

        except Exception as e:
            logger.error(f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº Ð¿Ð»Ð°Ð½Ð°: {e}")
            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ (Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½Ð¾)
            await self.safe_send(websocket, {
                'type': 'plan_settings_data',
                'settings': {
                    'workdays': default_workdays,
                    'visible_columns': default_visible_columns
                }
            })

    async def handle_save_shipping_summary_settings(self, websocket, data, session):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ð¿ÐµÑ€ÑÐ¾Ð½Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ ÑÐ²Ð¾Ð´Ð½Ð¾Ð¹ Ð¾Ñ‚Ð³Ñ€ÑƒÐ·ÐºÐ¸."""
        user_id = session.user_id
        visible_columns = data.get('visible_columns', [])
        priorities = data.get('priorities', {})

        if not isinstance(visible_columns, list):
            visible_columns = []
        if not isinstance(priorities, dict):
            priorities = {}

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO plan_settings (user_id, setting_key, setting_value)
                VALUES (?, 'shipping_summary_visible_columns', ?)
                ON CONFLICT(user_id, setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, json.dumps(visible_columns)))

            cursor.execute('''
                INSERT INTO plan_settings (user_id, setting_key, setting_value)
                VALUES (?, 'shipping_summary_priorities', ?)
                ON CONFLICT(user_id, setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, json.dumps(priorities)))

            conn.commit()
            conn.close()

            await websocket.send(json.dumps({
                'type': 'shipping_summary_settings_saved',
                'success': True
            }))
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº ÑÐ²Ð¾Ð´Ð½Ð¾Ð¹: {e}")
            await websocket.send(json.dumps({
                'type': 'shipping_summary_settings_saved',
                'success': False,
                'error': str(e)
            }))

    async def handle_get_shipping_summary_settings(self, websocket, session):
        """Ð—Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ Ð¿ÐµÑ€ÑÐ¾Ð½Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ ÑÐ²Ð¾Ð´Ð½Ð¾Ð¹ Ð¾Ñ‚Ð³Ñ€ÑƒÐ·ÐºÐ¸."""
        user_id = session.user_id
        default_visible_columns = [
            'article_nr', 'name', 'category', 'quantity', 'stock',
            'difference', 'coverage_percent', 'priority', 'comment'
        ]

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT setting_key, setting_value
                FROM plan_settings
                WHERE user_id = ?
                AND setting_key IN ('shipping_summary_visible_columns', 'shipping_summary_priorities')
            ''', (user_id,))

            settings = {}
            for row in cursor.fetchall():
                key = row[0]
                raw_val = row[1]
                try:
                    settings[key] = json.loads(raw_val) if raw_val else None
                except Exception:
                    settings[key] = None

            conn.close()

            visible = settings.get('shipping_summary_visible_columns')
            if not isinstance(visible, list) or not visible:
                visible = default_visible_columns

            priorities = settings.get('shipping_summary_priorities')
            if not isinstance(priorities, dict):
                priorities = {}

            await websocket.send(json.dumps({
                'type': 'shipping_summary_settings_data',
                'settings': {
                    'visible_columns': visible,
                    'priorities': priorities
                }
            }))
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº ÑÐ²Ð¾Ð´Ð½Ð¾Ð¹: {e}")
            await websocket.send(json.dumps({
                'type': 'shipping_summary_settings_data',
                'settings': {
                    'visible_columns': default_visible_columns,
                    'priorities': {}
                }
            }))

    async def handle_save_admin_orders_settings(self, websocket, data, session):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ð¿ÐµÑ€ÑÐ¾Ð½Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ 'Ð’ÑÐµ Ð·Ð°ÐºÐ°Ð·Ñ‹'."""
        user_id = session.user_id
        visible_columns = data.get('visible_columns', [])
        if not isinstance(visible_columns, list):
            visible_columns = []
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO plan_settings (user_id, setting_key, setting_value)
                VALUES (?, 'admin_orders_visible_columns', ?)
                ON CONFLICT(user_id, setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, json.dumps(visible_columns)))
            conn.commit()
            conn.close()
            await websocket.send(json.dumps({
                'type': 'admin_orders_settings_saved',
                'success': True
            }))
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²: {e}")
            await websocket.send(json.dumps({
                'type': 'admin_orders_settings_saved',
                'success': False,
                'error': str(e)
            }))

    async def handle_get_admin_orders_settings(self, websocket, session):
        """Ð—Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ Ð¿ÐµÑ€ÑÐ¾Ð½Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ 'Ð’ÑÐµ Ð·Ð°ÐºÐ°Ð·Ñ‹'."""
        user_id = session.user_id
        default_visible_columns = [
            'id', 'time', 'client', 'email', 'progress', 'status', 'wh',
            'lbl', 'route', 'sum', 'invoice', 'box', 'date'
        ]
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT setting_value
                FROM plan_settings
                WHERE user_id = ?
                AND setting_key = 'admin_orders_visible_columns'
                LIMIT 1
            ''', (user_id,))
            row = cursor.fetchone()
            conn.close()

            visible = default_visible_columns
            if row and row[0]:
                try:
                    parsed = json.loads(row[0])
                    if isinstance(parsed, list) and parsed:
                        visible = parsed
                except Exception:
                    pass

            await websocket.send(json.dumps({
                'type': 'admin_orders_settings_data',
                'settings': {
                    'visible_columns': visible
                }
            }))
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²: {e}")
            await websocket.send(json.dumps({
                'type': 'admin_orders_settings_data',
                'settings': {
                    'visible_columns': default_visible_columns
                }
            }))

    async def handle_search_warehouse_clients(self, websocket, data):
        """ÐŸÐ¾Ð¸ÑÐº ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² Ð´Ð»Ñ Ð²ÐºÐ»Ð°Ð´ÐºÐ¸ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ ÑÐºÐ»Ð°Ð´Ð°."""
        query = str(data.get('query', '') or '').strip()
        try:
            with self.db.safe_connection() as conn:
                cursor = conn.cursor()
                if query:
                    like = f"%{query}%"
                    cursor.execute("""
                        SELECT client_id, client_name
                        FROM client_routes
                        WHERE client_id LIKE ? OR client_name LIKE ?
                        ORDER BY client_name
                        LIMIT 50
                    """, (like, like))
                else:
                    cursor.execute("""
                        SELECT client_id, client_name
                        FROM client_routes
                        ORDER BY client_name
                    """)
                rows = cursor.fetchall()
            clients = [{'client_id': str(r[0]), 'client_name': str(r[1] or '')} for r in rows]
            await websocket.send(json.dumps({
                'type': 'warehouse_clients_search_result',
                'query': query,
                'clients': clients
            }))
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ð¾Ð¸ÑÐºÐ° ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² ÑÐºÐ»Ð°Ð´Ð°: {e}")
            await websocket.send(json.dumps({
                'type': 'warehouse_clients_search_result',
                'query': query,
                'clients': []
            }))

    async def handle_get_warehouse_print_settings(self, websocket):
        """Ð—Ð°Ð³Ñ€ÑƒÐ·Ð¸Ñ‚ÑŒ Ð³Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ Ð¿Ð¾ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼ Ð´Ð»Ñ ÑÐºÐ»Ð°Ð´Ð°."""
        default_settings = {
            '10054': {
                'language': 'SchÃ¤fer (10054)',
                'use_conditional': False,
                'client_name': 'Intermarkt SchÃ¤fer'
            }
        }
        try:
            with self.db.safe_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT setting_value
                    FROM plan_settings
                    WHERE user_id IS NULL AND setting_key = 'warehouse_print_client_settings'
                    ORDER BY rowid DESC
                    LIMIT 1
                """)
                row = cursor.fetchone()
                if row and row[0]:
                    try:
                        settings = json.loads(row[0])
                    except Exception:
                        settings = {}
                else:
                    settings = {}

                if not isinstance(settings, dict):
                    settings = {}

                # ÐœÐ¸Ð³Ñ€Ð°Ñ†Ð¸Ñ: Ð¿ÐµÑ€ÐµÐ½Ð¾Ñ ÑÑ‚Ð°Ñ€Ð¾Ð¹ Ð»Ð¾Ð³Ð¸ÐºÐ¸ SchÃ¤fer Ð² Ð½Ð¾Ð²ÑƒÑŽ Ð²ÐºÐ»Ð°Ð´ÐºÑƒ.
                for k, v in default_settings.items():
                    if k not in settings:
                        settings[k] = v

                selected_ids = list(settings.keys())
                clients = []
                if selected_ids:
                    placeholders = ",".join(["?"] * len(selected_ids))
                    cursor.execute(f"""
                        SELECT client_id, client_name
                        FROM client_routes
                        WHERE client_id IN ({placeholders})
                    """, selected_ids)
                    names_map = {str(r[0]): str(r[1] or '') for r in cursor.fetchall()}
                    for cid in selected_ids:
                        cname = names_map.get(str(cid), settings.get(cid, {}).get('client_name', ''))
                        clients.append({'client_id': str(cid), 'client_name': cname})
                        if isinstance(settings.get(cid), dict):
                            settings[cid]['client_name'] = cname

            await websocket.send(json.dumps({
                'type': 'warehouse_print_settings_data',
                'settings': settings,
                'selected_clients': clients
            }))
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²: {e}")
            await websocket.send(json.dumps({
                'type': 'warehouse_print_settings_data',
                'settings': default_settings,
                'selected_clients': [{'client_id': '10054', 'client_name': 'Intermarkt SchÃ¤fer'}]
            }))

    async def handle_save_warehouse_print_settings(self, websocket, data):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ð³Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ Ð¿Ð¾ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼ Ð´Ð»Ñ ÑÐºÐ»Ð°Ð´Ð°."""
        settings = data.get('settings', {})
        if not isinstance(settings, dict):
            settings = {}
        try:
            with self.db.safe_connection() as conn:
                cursor = conn.cursor()
                # SQLite Ð½Ðµ ÑÑ‡Ð¸Ñ‚Ð°ÐµÑ‚ NULL = NULL Ð² PK, Ð¿Ð¾ÑÑ‚Ð¾Ð¼Ñƒ Ð´ÐµÐ»Ð°ÐµÐ¼ ÑÐ²Ð½ÑƒÑŽ Ð·Ð°Ð¼ÐµÐ½Ñƒ Ð³Ð»Ð¾Ð±Ð°Ð»ÑŒÐ½Ð¾Ð¹ Ð·Ð°Ð¿Ð¸ÑÐ¸.
                cursor.execute("""
                    DELETE FROM plan_settings
                    WHERE user_id IS NULL AND setting_key = 'warehouse_print_client_settings'
                """)
                cursor.execute("""
                    INSERT INTO plan_settings (user_id, setting_key, setting_value, updated_at)
                    VALUES (NULL, 'warehouse_print_client_settings', ?, CURRENT_TIMESTAMP)
                """, (json.dumps(settings, ensure_ascii=False),))
                conn.commit()

            await websocket.send(json.dumps({
                'type': 'warehouse_print_settings_saved',
                'success': True
            }))
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ Ð½Ð°ÑÑ‚Ñ€Ð¾ÐµÐº Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²: {e}")
            await websocket.send(json.dumps({
                'type': 'warehouse_print_settings_saved',
                'success': False,
                'error': str(e)
            }))

    def _default_backup_settings(self, target: str) -> dict:
        """Ð”ÐµÑ„Ð¾Ð»Ñ‚Ð½Ñ‹Ðµ Ð½Ð°ÑÑ‚Ñ€Ð¾Ð¹ÐºÐ¸ Ð°Ð²Ñ‚Ð¾Ð±ÑÐºÐ°Ð¿Ð° Ð´Ð»Ñ target."""
        if target == 'documents':
            default_time = "03:30"
        else:
            default_time = "03:00"
        return {
            'enabled': False,
            'mode': 'daily',  # daily | weekly
            'time': default_time,  # HH:MM
            'weekday': 6,  # 0=Mon ... 6=Sun (Ð´Ð»Ñ weekly)
            'last_run_at': None
        }

    def _backup_setting_key(self, target: str) -> str:
        if target == 'documents':
            return 'backup_documents_settings'
        return 'backup_system_settings'

    def _normalize_backup_settings(self, target: str, incoming: dict) -> dict:
        base = self._default_backup_settings(target)
        if not isinstance(incoming, dict):
            return base

        enabled = bool(incoming.get('enabled', base['enabled']))
        mode = str(incoming.get('mode', base['mode'])).lower().strip()
        if mode not in ('daily', 'weekly'):
            mode = 'daily'

        time_val = str(incoming.get('time', base['time'])).strip()
        try:
            hh, mm = time_val.split(':')
            hh_i = max(0, min(23, int(hh)))
            mm_i = max(0, min(59, int(mm)))
            time_val = f"{hh_i:02d}:{mm_i:02d}"
        except Exception:
            time_val = base['time']

        try:
            weekday = int(incoming.get('weekday', base['weekday']))
        except Exception:
            weekday = base['weekday']
        weekday = max(0, min(6, weekday))

        last_run_at = incoming.get('last_run_at')
        if last_run_at is not None:
            last_run_at = str(last_run_at)

        return {
            'enabled': enabled,
            'mode': mode,
            'time': time_val,
            'weekday': weekday,
            'last_run_at': last_run_at
        }

    def _load_backup_settings_from_db(self, target: str) -> dict:
        key = self._backup_setting_key(target)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT setting_value
                FROM plan_settings
                WHERE user_id IS NULL AND setting_key = ?
                ORDER BY rowid DESC
                LIMIT 1
            """, (key,))
            row = cursor.fetchone()
            if not row or not row[0]:
                return self._default_backup_settings(target)
            try:
                raw = json.loads(row[0])
            except Exception:
                raw = {}
            return self._normalize_backup_settings(target, raw)

    def _load_all_backup_settings_from_db(self) -> dict:
        return {
            'system': self._load_backup_settings_from_db('system'),
            'documents': self._load_backup_settings_from_db('documents')
        }

    def _save_backup_settings_to_db(self, target: str, settings: dict):
        key = self._backup_setting_key(target)
        normalized = self._normalize_backup_settings(target, settings)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # Ð”Ð»Ñ NULL user_id Ð´ÐµÐ»Ð°ÐµÐ¼ DELETE + INSERT (Ð¸Ð·-Ð·Ð° SQLite NULL Ð² PK)
            cursor.execute("""
                DELETE FROM plan_settings
                WHERE user_id IS NULL AND setting_key = ?
            """, (key,))
            cursor.execute("""
                INSERT INTO plan_settings (user_id, setting_key, setting_value, updated_at)
                VALUES (NULL, ?, ?, CURRENT_TIMESTAMP)
            """, (key, json.dumps(normalized, ensure_ascii=False)))
            conn.commit()

    def _build_backup_destination(self, target: str, now: datetime):
        date_part = now.strftime('%Y-%m-%d')
        time_part = now.strftime('%H-%M-%S')
        if target == 'documents':
            source = DOCUMENTS_BACKUP_SOURCE
            destination = BACKUP_ROOT_PATH / "documents" / date_part / time_part / source.name
        else:
            source = SYSTEM_BACKUP_SOURCE
            destination = BACKUP_ROOT_PATH / date_part / time_part / source.name
        return source, destination

    def _get_backup_base_folder(self, target: str) -> Path:
        if target == 'documents':
            return BACKUP_ROOT_PATH / "documents"
        return BACKUP_ROOT_PATH

    def _list_backup_points(self, target: str) -> list:
        """Ð¡Ð¿Ð¸ÑÐ¾Ðº backup-ÐºÐ¾Ð¿Ð¸Ð¹: Ð¾Ð´Ð½Ð° Ð·Ð°Ð¿Ð¸ÑÑŒ = date/time ÑÐ»Ð¾Ñ‚."""
        base = self._get_backup_base_folder(target)
        points = []
        if not base.exists():
            return points

        for date_dir in base.iterdir():
            if not date_dir.is_dir():
                continue
            # Ð”Ð»Ñ system Ð² ÐºÐ¾Ñ€Ð½Ðµ backup Ð¼Ð¾Ð¶ÐµÑ‚ Ð»ÐµÐ¶Ð°Ñ‚ÑŒ ÑÐ»ÑƒÐ¶ÐµÐ±Ð½Ð°Ñ Ð¿Ð°Ð¿ÐºÐ° documents
            if target == 'system' and date_dir.name.lower() == 'documents':
                continue
            for time_dir in date_dir.iterdir():
                if not time_dir.is_dir():
                    continue
                dt_obj = None
                try:
                    dt_obj = datetime.strptime(f"{date_dir.name} {time_dir.name}", "%Y-%m-%d %H-%M-%S")
                except Exception:
                    # ÐŸÑ€Ð¾Ð¿ÑƒÑÐºÐ°ÐµÐ¼ Ð½ÐµÑÑ‚Ð°Ð½Ð´Ð°Ñ€Ñ‚Ð½Ñ‹Ðµ Ð¿Ð°Ð¿ÐºÐ¸
                    continue

                if target == 'documents':
                    content_dir = time_dir / DOCUMENTS_BACKUP_SOURCE.name
                else:
                    content_dir = time_dir / SYSTEM_BACKUP_SOURCE.name

                points.append({
                    'target': target,
                    'date': date_dir.name,
                    'time': time_dir.name,
                    'datetime': dt_obj,
                    'slot_path': str(time_dir),
                    'content_path': str(content_dir)
                })

        points.sort(key=lambda x: x['datetime'])
        return points

    def _cleanup_backups(self, target: str, keep_count: int) -> list:
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÑÑ‚Ð°Ñ€Ñ‹Ðµ backup-ÐºÐ¾Ð¿Ð¸Ð¸, Ð¾ÑÑ‚Ð°Ð²Ð¸Ñ‚ÑŒ keep_count Ð¿Ð¾ÑÐ»ÐµÐ´Ð½Ð¸Ñ…."""
        points = self._list_backup_points(target)
        if keep_count < 0:
            keep_count = 0
        to_delete = points[:-keep_count] if keep_count > 0 else points[:]
        deleted = []
        for item in to_delete:
            slot_path = Path(item['slot_path'])
            try:
                if slot_path.exists():
                    shutil.rmtree(slot_path, ignore_errors=False)
                    deleted.append(str(slot_path))
            except Exception as e:
                logger.warning(f"Cleanup backup failed for {slot_path}: {e}")

        # ÐŸÑƒÑÑ‚Ñ‹Ðµ date-Ð¿Ð°Ð¿ÐºÐ¸ Ñ‚Ð¾Ð¶Ðµ ÑƒÐ´Ð°Ð»ÑÐµÐ¼
        base = self._get_backup_base_folder(target)
        if base.exists():
            for date_dir in base.iterdir():
                if not date_dir.is_dir():
                    continue
                try:
                    if not any(date_dir.iterdir()):
                        date_dir.rmdir()
                except Exception:
                    pass
        return deleted

    def _build_backup_history_payload(self) -> list:
        items = []
        for target in ('system', 'documents'):
            points = self._list_backup_points(target)
            for p in points:
                items.append({
                    'target': target,
                    'date': p['date'],
                    'time': p['time'],
                    'path': p['content_path']
                })
        items.sort(key=lambda x: f"{x['date']} {x['time']}", reverse=True)
        return items

    def _run_backup_sync(self, target: str, trigger: str = 'manual') -> dict:
        started = datetime.now()
        source, destination = self._build_backup_destination(target, started)
        result = {
            'target': target,
            'trigger': trigger,
            'source': str(source),
            'destination': str(destination),
            'started_at': started.isoformat(),
            'success': False
        }
        try:
            if not source.exists():
                raise FileNotFoundError(f"Source not found: {source}")

            destination.parent.mkdir(parents=True, exist_ok=True)
            # SQLite WAL/SHM могут появляться и исчезать во время копирования.
            # Игнорируем их в backup, чтобы не падать на FileNotFoundError race.
            ignore_patterns = shutil.ignore_patterns('*.db-wal', '*.db-shm')
            shutil.copytree(source, destination, dirs_exist_ok=False, ignore=ignore_patterns)

            # ÐŸÐ¾Ð»Ð¸Ñ‚Ð¸ÐºÐ° Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ:
            # system: Ð¼Ð°ÐºÑÐ¸Ð¼ÑƒÐ¼ 6 ÐºÐ¾Ð¿Ð¸Ð¹
            # documents: Ð²ÑÐµÐ³Ð´Ð° Ñ‚Ð¾Ð»ÑŒÐºÐ¾ 1 ÐºÐ¾Ð¿Ð¸Ñ (Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÑÑ)
            if target == 'documents':
                deleted = self._cleanup_backups('documents', keep_count=1)
            else:
                deleted = self._cleanup_backups('system', keep_count=6)
            if deleted:
                result['cleanup_deleted'] = deleted

            result['success'] = True
            result['finished_at'] = datetime.now().isoformat()
            return result
        except Exception as e:
            result['error'] = str(e)
            result['finished_at'] = datetime.now().isoformat()
            logger.error(f"Backup failed [{target}]: {e}")
            return result

    def _is_backup_due(self, target: str, settings: dict, now_dt: datetime) -> tuple[bool, Optional[str]]:
        if not settings.get('enabled'):
            return False, None

        mode = settings.get('mode', 'daily')
        time_str = settings.get('time', '03:00')
        try:
            hh, mm = [int(x) for x in str(time_str).split(':', 1)]
        except Exception:
            hh, mm = 3, 0

        if now_dt.hour != hh or now_dt.minute != mm:
            return False, None

        if mode == 'weekly':
            weekday = int(settings.get('weekday', 6))
            if now_dt.weekday() != weekday:
                return False, None

        run_key = f"{now_dt.strftime('%Y-%m-%d %H:%M')}|{mode}"
        if self._backup_last_run_keys.get(target) == run_key:
            return False, run_key

        return True, run_key

    async def handle_get_backup_settings(self, websocket, session):
        if session.role != 'admin':
            await self.safe_send(websocket, {'type': 'error', 'message': 'ÐÐµÐ´Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾ Ð¿Ñ€Ð°Ð²'})
            return
        try:
            settings = await self._run_sync(self._load_all_backup_settings_from_db)
            await self.safe_send(websocket, {
                'type': 'backup_settings_data',
                'settings': settings
            })
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ backup settings: {e}")
            await self.safe_send(websocket, {
                'type': 'backup_settings_data',
                'settings': {
                    'system': self._default_backup_settings('system'),
                    'documents': self._default_backup_settings('documents')
                }
            })

    async def handle_get_backup_history(self, websocket, session):
        if session.role != 'admin':
            await self.safe_send(websocket, {'type': 'error', 'message': 'ÐÐµÐ´Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾ Ð¿Ñ€Ð°Ð²'})
            return
        try:
            items = await self._run_sync(self._build_backup_history_payload)
            await self.safe_send(websocket, {
                'type': 'backup_history_data',
                'items': items
            })
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ backup history: {e}")
            await self.safe_send(websocket, {
                'type': 'backup_history_data',
                'items': []
            })

    async def handle_save_backup_settings(self, websocket, data, session):
        if session.role != 'admin':
            await self.safe_send(websocket, {'type': 'error', 'message': 'ÐÐµÐ´Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾ Ð¿Ñ€Ð°Ð²'})
            return
        target = str(data.get('target', '')).strip().lower()
        if target not in ('system', 'documents'):
            await self.safe_send(websocket, {'type': 'error', 'message': 'ÐÐµÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ñ‹Ð¹ Ñ‚Ð¸Ð¿ Ð±ÑÐºÐ°Ð¿Ð°'})
            return
        incoming_settings = data.get('settings', {})
        normalized = self._normalize_backup_settings(target, incoming_settings)
        try:
            await self._run_sync(self._save_backup_settings_to_db, target, normalized)
            await self.safe_send(websocket, {
                'type': 'backup_settings_saved',
                'target': target,
                'settings': normalized,
                'success': True
            })
        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ backup settings ({target}): {e}")
            await self.safe_send(websocket, {
                'type': 'backup_settings_saved',
                'target': target,
                'success': False,
                'error': str(e)
            })

    async def handle_run_backup_now(self, websocket, data, session):
        if session.role != 'admin':
            await self.safe_send(websocket, {'type': 'error', 'message': 'ÐÐµÐ´Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾ Ð¿Ñ€Ð°Ð²'})
            return
        target = str(data.get('target', '')).strip().lower()
        if target not in ('system', 'documents'):
            await self.safe_send(websocket, {'type': 'error', 'message': 'ÐÐµÐºÐ¾Ñ€Ñ€ÐµÐºÑ‚Ð½Ñ‹Ð¹ Ñ‚Ð¸Ð¿ Ð±ÑÐºÐ°Ð¿Ð°'})
            return
        result = await self._run_sync(self._run_backup_sync, target, 'manual')
        await self.safe_send(websocket, {
            'type': 'backup_now_result',
            'result': result
        })
        await self.sessions.broadcast_to_admins({
            'type': 'backup_status_update',
            'result': result
        })
        items = await self._run_sync(self._build_backup_history_payload)
        await self.sessions.broadcast_to_admins({
            'type': 'backup_history_data',
            'items': items
        })

    def _build_server_status_payload(self) -> dict:
        sessions_data = []
        for sid, s in self.sessions.sessions.items():
            remote_ip = "-"
            try:
                ra = getattr(s.websocket, 'remote_address', None)
                if isinstance(ra, tuple) and ra:
                    remote_ip = str(ra[0])
                elif ra:
                    remote_ip = str(ra)
            except Exception:
                pass

            sessions_data.append({
                'session_id': sid,
                'session_short': sid[:8],
                'username': s.username,
                'role': s.role,
                'warehouse_id': s.warehouse_id or '-',
                'connected_at': s.connected_at,
                'remote_ip': remote_ip
            })

        sessions_data.sort(key=lambda x: x.get('connected_at', ''), reverse=True)

        logs_tail = []
        try:
            log_path = Path('server_unified.log')
            if log_path.exists():
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    logs_tail = list(deque(f, maxlen=250))
                logs_tail = [line.rstrip('\n') for line in logs_tail]
        except Exception as e:
            logs_tail = [f'Failed to read logs: {e}']

        return {
            'sessions': sessions_data,
            'stats': {
                'active_total': len(self.sessions.sessions),
                'admins': len(self.sessions.admin_clients),
                'operators': len(self.sessions.operator_clients),
                'warehouses': sum(len(v) for v in self.sessions.warehouse_clients.values())
            },
            'logs_tail': logs_tail
        }

    async def handle_get_server_status(self, websocket, session):
        if session.role != 'admin':
            await self.safe_send(websocket, {'type': 'error', 'message': 'ÐÐµÐ´Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾ Ð¿Ñ€Ð°Ð²'})
            return
        payload = await self._run_sync(self._build_server_status_payload)
        await self.safe_send(websocket, {
            'type': 'server_status_data',
            **payload
        })

    async def handle_disconnect_session(self, websocket, data, session):
        if session.role != 'admin':
            await self.safe_send(websocket, {'type': 'error', 'message': 'ÐÐµÐ´Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾ Ð¿Ñ€Ð°Ð²'})
            return

        target_session_id = str(data.get('session_id', '')).strip()
        if not target_session_id:
            await self.safe_send(websocket, {'type': 'disconnect_session_result', 'success': False, 'error': 'session_id required'})
            return

        target = self.sessions.sessions.get(target_session_id)
        if not target:
            await self.safe_send(websocket, {'type': 'disconnect_session_result', 'success': False, 'error': 'Session not found'})
            return

        try:
            await self.safe_send(target.websocket, {
                'type': 'force_disconnect',
                'reason': f'ÐžÑ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¾ Ð°Ð´Ð¼Ð¸Ð½Ð¾Ð¼: {session.username}',
                'action': 'close_app'
            })
        except Exception:
            pass

        try:
            await target.websocket.close()
        except Exception:
            pass

        self.sessions.remove_session(target.websocket)
        await self.safe_send(websocket, {'type': 'disconnect_session_result', 'success': True})

        payload = await self._run_sync(self._build_server_status_payload)
        await self.sessions.broadcast_to_admins({'type': 'server_status_data', **payload})

    def _restart_current_process(self):
        """ÐŸÐ¾Ð»Ð½Ñ‹Ð¹ Ð¿ÐµÑ€ÐµÐ·Ð°Ð¿ÑƒÑÐº Ð¿Ñ€Ð¾Ñ†ÐµÑÑÐ° ÑÐµÑ€Ð²ÐµÑ€Ð°."""
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            logger.critical(f"Server restart failed: {e}", exc_info=True)
            os._exit(1)

    async def handle_restart_server(self, websocket, data, session):
        if session.role != 'admin':
            await self.safe_send(websocket, {'type': 'error', 'message': 'ÐÐµÐ´Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾ Ð¿Ñ€Ð°Ð²'})
            return

        await self.safe_send(websocket, {'type': 'server_restart_ack', 'success': True})
        await self.sessions.broadcast_to_admins({
            'type': 'server_restarting',
            'by': session.username,
            'at': datetime.now().isoformat()
        })

        def _delayed_restart():
            time.sleep(1.0)
            self._restart_current_process()

        threading.Thread(target=_delayed_restart, daemon=True).start()

    async def backup_scheduler_loop(self):
        """Ð¤Ð¾Ð½Ð¾Ð²Ñ‹Ð¹ Ð¿Ð»Ð°Ð½Ð¸Ñ€Ð¾Ð²Ñ‰Ð¸Ðº Ð°Ð²Ñ‚Ð¾Ð±ÑÐºÐ°Ð¿Ð¾Ð² (system/documents)."""
        logger.info("Backup scheduler loop started")
        while True:
            try:
                await asyncio.sleep(30)
                now_dt = datetime.now()
                settings_map = await self._run_sync(self._load_all_backup_settings_from_db)

                for target in ('system', 'documents'):
                    settings = settings_map.get(target, self._default_backup_settings(target))
                    due, run_key = self._is_backup_due(target, settings, now_dt)
                    if not due:
                        continue

                    logger.info(f"[BACKUP] Auto backup due: {target} at {now_dt.strftime('%Y-%m-%d %H:%M')}")
                    result = await self._run_sync(self._run_backup_sync, target, 'auto')
                    self._backup_last_run_keys[target] = run_key

                    if result.get('success'):
                        settings['last_run_at'] = result.get('finished_at')
                        await self._run_sync(self._save_backup_settings_to_db, target, settings)

                    await self.sessions.broadcast_to_admins({
                        'type': 'backup_status_update',
                        'result': result
                    })
                    items = await self._run_sync(self._build_backup_history_payload)
                    await self.sessions.broadcast_to_admins({
                        'type': 'backup_history_data',
                        'items': items
                    })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Backup scheduler error: {e}")

    # ============================================
    # ÐžÐ‘Ð ÐÐ‘ÐžÐ¢Ð§Ð˜ÐšÐ˜ BOM Ð˜ ÐžÐ¡Ð¢ÐÐ¢ÐšÐžÐ’
    # ============================================
    async def handle_get_recipe_bom(self, websocket, data):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ BOM (ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ñ‹) Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°"""
        article_nr = data.get('article_nr')

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # Ð˜Ð¡ÐŸÐ ÐÐ’Ð›Ð•ÐÐž: Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ Ð¿Ñ€Ð°Ð²Ð¸Ð»ÑŒÐ½Ð¾Ðµ Ð¸Ð¼Ñ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ parent_article_nr
            cursor.execute('''
                SELECT component_id, component_name, quantity, unit
                FROM recipe_components
                WHERE parent_article_nr = ?
                ORDER BY component_name
            ''', (article_nr,))

            components = []
            for row in cursor.fetchall():
                components.append({
                    'component_id': row[0],
                    'component_name': row[1],
                    'quantity': row[2],
                    'unit': row[3]
                })

            conn.close()
            await websocket.send(json.dumps({
                'type': 'recipe_bom_data',
                'article_nr': article_nr,
                'components': components
            }))

        except Exception as e:
            logger.error(f"BOM Load Error: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ð¾Ð²: {str(e)}'
            }))

    async def handle_get_dough_composition(self, websocket, data):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÑÐ¾ÑÑ‚Ð°Ð² ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ð° (Ð²Ð»Ð¾Ð¶ÐµÐ½Ð½Ñ‹Ðµ ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ñ‹)"""
        dough_id = data.get('dough_id')

        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT dc.child_dough_id, dt.name, dc.quantity, dc.unit
                FROM dough_components dc
                LEFT JOIN dough_types dt ON dc.child_dough_id = dt.dough_id
                WHERE dc.parent_dough_id = ?
                ORDER BY dt.name
            ''', (dough_id,))

            components = []
            for row in cursor.fetchall():
                components.append({
                    'child_dough_id': row[0],
                    'child_name': row[1] if row[1] else row[0],
                    'quantity': row[2],
                    'unit': row[3]
                })

            conn.close()

            logger.info(f"ðŸ“¦ Ð¡Ð¾ÑÑ‚Ð°Ð² Ð·Ð°Ð³Ñ€ÑƒÐ¶ÐµÐ½ Ð´Ð»Ñ ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ð° {dough_id}: {len(components)} Ð²Ð»Ð¾Ð¶ÐµÐ½Ð½Ñ‹Ñ… ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ð¾Ð²")

            await websocket.send(json.dumps({
                'type': 'dough_composition_data',
                'dough_id': dough_id,
                'components': components
            }))

        except Exception as e:
            logger.error(f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ ÑÐ¾ÑÑ‚Ð°Ð²Ð° ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ð°: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ ÑÐ¾ÑÑ‚Ð°Ð²Ð°: {str(e)}'
            }))

    async def handle_save_daily_stock(self, websocket, data):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸ Ð½Ð° Ð´Ð°Ñ‚Ñƒ"""
        date = data.get('date')
        stocks = data.get('stocks', [])

        try:
            stock_mgr = VirtualStockManager(database=self.db)

            for stock_data in stocks:
                stock_mgr.set_stock(
                    date=date,
                    component_id=stock_data['component_id'],
                    component_name=stock_data['component_name'],
                    quantity=stock_data['quantity'],
                    unit=stock_data.get('unit', 'ÑˆÑ‚'),
                    source=stock_data.get('source', 'manual'),
                    notes=stock_data.get('notes')
                )

            logger.info(f"ðŸ’¾ ÐžÑÑ‚Ð°Ñ‚ÐºÐ¸ ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ñ‹ Ð½Ð° {date}: {len(stocks)} ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ð¾Ð²")

            await websocket.send(json.dumps({
                'type': 'daily_stock_saved',
                'date': date,
                'count': len(stocks)
            }))

        except Exception as e:
            logger.error(f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¾Ð²: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¾Ð²: {str(e)}'
            }))

    async def handle_get_daily_stock(self, websocket, data):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸ Ð½Ð° Ð´Ð°Ñ‚Ñƒ"""
        date = data.get('date')

        try:
            stock_mgr = VirtualStockManager(database=self.db)

            stocks = stock_mgr.get_all_stock_for_date(date)

            logger.info(f"ðŸ“¦ ÐžÑÑ‚Ð°Ñ‚ÐºÐ¸ Ð·Ð°Ð³Ñ€ÑƒÐ¶ÐµÐ½Ñ‹ Ð½Ð° {date}: {len(stocks)} ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ð¾Ð²")

            await websocket.send(json.dumps({
                'type': 'daily_stock_data',
                'date': date,
                'stocks': stocks
            }))

        except Exception as e:
            logger.error(f"âŒ ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¾Ð²: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¾Ð²: {str(e)}'
            }))

    # ============================================
    # ÐžÐ‘Ð ÐÐ‘ÐžÐ¢Ð§Ð˜ÐšÐ˜ Ð Ð•Ð¦Ð•ÐŸÐ¢ÐžÐ’ (ÐŸÐ ÐžÐ˜Ð—Ð’ÐžÐ”Ð¡Ð¢Ð’Ðž)
    # ============================================
    async def handle_get_recipes(self, websocket):
        """ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº Ñ‚Ð¸Ð¿Ð¾Ð² Ñ‚ÐµÑÑ‚Ð° Ð¸ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð²"""
        with self.db.safe_connection() as conn:
            cursor = conn.cursor()

            # 1. Ð¢Ð¸Ð¿Ñ‹ Ñ‚ÐµÑÑ‚Ð° Ñ Ð¸Ð¼ÐµÐ½Ð°Ð¼Ð¸ Ñ€ÐµÑÑƒÑ€ÑÐ¾Ð²
            cursor.execute("""
                SELECT dt.*, fr.resource_name
                FROM dough_types dt
                LEFT JOIN factory_resources fr ON dt.resource_id = fr.resource_id
                ORDER BY dt.name
            """)
            dough_types = [dict(row) for row in cursor.fetchall()]

            # 2. Ð ÐµÑ†ÐµÐ¿Ñ‚Ñ‹ (Ð’Ð¡Ð• â€” Ð°Ð´Ð¼Ð¸Ð½ Ð²Ð¸Ð´Ð¸Ñ‚ Ð¸ Ð½ÐµÐ°ÐºÑ‚Ð¸Ð²Ð½Ñ‹Ðµ, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð¼Ð¾Ð³ Ð²ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ Ð¾Ð±Ñ€Ð°Ñ‚Ð½Ð¾)
            try:
                cursor.execute("SELECT * FROM recipes ORDER BY COALESCE(is_new, 0) DESC, active DESC, article_nr")
            except:
                cursor.execute("SELECT * FROM recipes ORDER BY article_nr")
            recipes = [dict(row) for row in cursor.fetchall()]

            # 3. ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð½Ð°Ð·Ð²Ð°Ð½Ð¸Ñ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¹ Ð´Ð»Ñ Ð²Ñ‹Ð¿Ð°Ð´Ð°ÑŽÑ‰ÐµÐ³Ð¾ ÑÐ¿Ð¸ÑÐºÐ°
            categories = self.db.get_category_names()

        await websocket.send(json.dumps({
            'type': 'recipes_data',
            'dough_types': dough_types,
            'recipes': recipes,
            'categories': categories
        }))

    async def handle_save_dough_type(self, websocket, data):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚ Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð°"""
        with self.db.safe_connection() as conn:
            cursor = conn.cursor()

            unit = data.get('unit', 'Ð³Ñ€')
            workshop = data.get('workshop', 'ÐžÑÐ½Ð¾Ð²Ð½Ð¾Ð¹ Ñ†ÐµÑ…')
            resource_id = data.get('resource_id', 1)  # ÐŸÐ¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ ÐŸÐµÑ‡ÑŒ
            production_time_min = data.get('production_time_min', 0.0)  # Ð’Ñ€ÐµÐ¼Ñ Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð° Ð¿Ð°Ñ€Ñ‚Ð¸Ð¸
            dough_id = data['dough_id']

            cursor.execute('''
                INSERT OR REPLACE INTO dough_types (dough_id, name, batch_size, unit, workshop, resource_id, production_time_min, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (dough_id, data['name'], data['batch_size'], unit, workshop, resource_id, production_time_min, datetime.now().isoformat()))

            # Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ ÑÐ¾ÑÑ‚Ð°Ð² (Ð²Ð»Ð¾Ð¶ÐµÐ½Ð½Ñ‹Ðµ ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ñ‹)
            composition = data.get('composition', [])
            if composition is not None:
                # Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÑÑ‚Ð°Ñ€Ñ‹Ð¹ ÑÐ¾ÑÑ‚Ð°Ð²
                cursor.execute('DELETE FROM dough_components WHERE parent_dough_id = ?', (dough_id,))

                # Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð½Ð¾Ð²Ñ‹Ð¹ ÑÐ¾ÑÑ‚Ð°Ð²
                for comp in composition:
                    cursor.execute('''
                        INSERT INTO dough_components (parent_dough_id, child_dough_id, quantity, unit, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (dough_id, comp['child_dough_id'], comp['quantity'], comp['unit'],
                          datetime.now().isoformat(), datetime.now().isoformat()))

                logger.info(f"Saved composition for {dough_id}: {len(composition)} components")

            conn.commit()
            logger.info(f"Production component saved: {dough_id} - {data['batch_size']} {unit} (resource_id={resource_id}, time={production_time_min}min)")

        # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð²
        await self.handle_get_recipes(websocket)

    async def handle_delete_dough_type(self, websocket, data):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ñ‚Ð¸Ð¿ Ñ‚ÐµÑÑ‚Ð°"""
        dough_id = data['dough_id']

        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # ÐŸÑ€Ð¾Ð²ÐµÑ€Ð¸Ñ‚ÑŒ, Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ÑÑ Ð»Ð¸ ÑÑ‚Ð¾Ñ‚ Ñ‚Ð¸Ð¿ Ð² Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°Ñ…
            cursor.execute("SELECT COUNT(*) FROM recipes WHERE dough_id = ?", (dough_id,))
            count = cursor.fetchone()[0]

            if count > 0:
                await websocket.send(json.dumps({
                    'type': 'error',
                    'message': f'ÐÐµÐ²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ ÑƒÐ´Ð°Ð»Ð¸Ñ‚ÑŒ: {count} Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÑŽÑ‚ ÑÑ‚Ð¾Ñ‚ Ñ‚Ð¸Ð¿ Ñ‚ÐµÑÑ‚Ð°'
                }))
                conn.close()
                return

            # Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ
            cursor.execute("DELETE FROM dough_types WHERE dough_id = ?", (dough_id,))
            conn.commit()

            logger.info(f"Deleted dough type: {dough_id}")

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ñ‹Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð²
            await self.handle_get_recipes(websocket)

        except Exception as e:
            logger.error(f"Error deleting dough type: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'ÐžÑˆÐ¸Ð±ÐºÐ° ÑƒÐ´Ð°Ð»ÐµÐ½Ð¸Ñ: {str(e)}'
            }))
        finally:
            conn.close()

    async def handle_save_recipe(self, websocket, data):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ñ€ÐµÑ†ÐµÐ¿Ñ‚ Ñ‚Ð¾Ñ€Ñ‚Ð° (Ð˜Ð¡ÐŸÐ ÐÐ’Ð›Ð•ÐÐž: Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ Ð¸ active)"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ active Ð¸Ð· Ð´Ð°Ð½Ð½Ñ‹Ñ… (Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ 1)
        active = data.get('active', 1)
        freeze_mode = str(data.get('freeze_mode', '') or '')

        try:
            data['article_nr'] = self._resolve_recipe_article_nr_for_write(cursor, data.get('article_nr'))
            if not data['article_nr']:
                await websocket.send(json.dumps({'type': 'error', 'message': 'ÐŸÑƒÑÑ‚Ð¾Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»'}))
                return

            # Ð¡Ð½Ð°Ñ‡Ð°Ð»Ð° Ð¿Ñ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼, ÐµÑÑ‚ÑŒ Ð»Ð¸ Ð·Ð°Ð¿Ð¸ÑÑŒ
            cursor.execute("SELECT 1 FROM recipes WHERE article_nr = ?", (data['article_nr'],))
            exists = cursor.fetchone()

            if exists:
                cursor.execute('''
                    UPDATE recipes
                    SET name=?, dough_id=?, items_per_tray=?, packaging_id=?, category=?, active=?, freeze_mode=?, updated_at=?
                    WHERE article_nr=?
                ''', (
                    data['name'],
                    data['dough_id'],
                    data['items_per_tray'],
                    data['packaging_id'],
                    data['category'],
                    active,
                    freeze_mode,
                    datetime.now().isoformat(),
                    data['article_nr']
                ))
            else:
                cursor.execute('''
                    INSERT INTO recipes (article_nr, name, dough_id, items_per_tray, packaging_id, category, active, freeze_mode, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data['article_nr'],
                    data['name'],
                    data['dough_id'],
                    data['items_per_tray'],
                    data['packaging_id'],
                    data['category'],
                    active,
                    freeze_mode,
                    datetime.now().isoformat()
                ))
        
            conn.commit()
            logger.info(f"Recipe saved: {data['article_nr']} ({data['category']})")
        
            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ð¿Ð¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð¸Ðµ (Ð¾Ð¿Ñ†Ð¸Ð¾Ð½Ð°Ð»ÑŒÐ½Ð¾) Ð¸Ð»Ð¸ Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ
            await self.handle_get_recipes(websocket)
        
        except Exception as e:
            logger.error(f"Error saving recipe: {e}")
        finally:
            conn.close()

    async def handle_delete_recipe(self, websocket, data):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ñ€ÐµÑ†ÐµÐ¿Ñ‚ (Ð£ÐÐ˜Ð’Ð•Ð Ð¡ÐÐ›Ð¬ÐÐ«Ð™ ÐŸÐžÐ˜Ð¡Ðš)"""
        original_art = str(data.get('article_nr', '')).strip()
    
        # Ð“ÐµÐ½ÐµÑ€Ð¸Ñ€ÑƒÐµÐ¼ Ð²Ð°Ñ€Ð¸Ð°Ð½Ñ‚Ñ‹ Ð½Ð¾Ð¼ÐµÑ€Ð° (ÐºÐ°Ðº ÐµÑÑ‚ÑŒ, 5 Ð·Ð½Ð°ÐºÐ¾Ð², 6 Ð·Ð½Ð°ÐºÐ¾Ð²)
        candidates = [original_art]
    
        # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð²Ð°Ñ€Ð¸Ð°Ð½Ñ‚ Ñ 5 Ð·Ð½Ð°ÐºÐ°Ð¼Ð¸
        if original_art.isdigit():
            candidates.append(original_art.zfill(5))
            candidates.append(original_art.zfill(6)) # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð²Ð°Ñ€Ð¸Ð°Ð½Ñ‚ Ñ 6 Ð·Ð½Ð°ÐºÐ°Ð¼Ð¸ (000001)
        
        # Ð£Ð±Ð¸Ñ€Ð°ÐµÐ¼ Ð´ÑƒÐ±Ð»Ð¸ÐºÐ°Ñ‚Ñ‹
        candidates = list(set(candidates))
    
        logger.info(f"ÐŸÐ¾Ð¿Ñ‹Ñ‚ÐºÐ° ÑƒÐ´Ð°Ð»ÐµÐ½Ð¸Ñ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð°. ÐšÐ°Ð½Ð´Ð¸Ð´Ð°Ñ‚Ñ‹: {candidates}")

        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("PRAGMA foreign_keys = ON")
        
            deleted = False
        
            # ÐŸÑ€Ð¾Ð±ÑƒÐµÐ¼ ÑƒÐ´Ð°Ð»Ð¸Ñ‚ÑŒ ÐºÐ°Ð¶Ð´Ñ‹Ð¹ Ð²Ð°Ñ€Ð¸Ð°Ð½Ñ‚ Ð¿Ð¾ Ð¾Ñ‡ÐµÑ€ÐµÐ´Ð¸
            for art_nr in candidates:
                # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼, ÐµÑÑ‚ÑŒ Ð»Ð¸ Ñ‚Ð°ÐºÐ¾Ð¹ Ñ€ÐµÑ†ÐµÐ¿Ñ‚
                cursor.execute("SELECT 1 FROM recipes WHERE article_nr = ?", (art_nr,))
                if cursor.fetchone():
                    logger.info(f"ÐÐ°Ð¹Ð´ÐµÐ½ Ñ€ÐµÑ†ÐµÐ¿Ñ‚ Ð´Ð»Ñ ÑƒÐ´Ð°Ð»ÐµÐ½Ð¸Ñ: {art_nr}")
                
                    # Ð£Ð´Ð°Ð»ÑÐµÐ¼ ÑÐ²ÑÐ·Ð°Ð½Ð½Ñ‹Ðµ Ð·Ð°Ð¿Ð¸ÑÐ¸
                    cursor.execute("DELETE FROM recipe_components WHERE parent_article_nr = ?", (art_nr,))
                    cursor.execute("DELETE FROM product_resource_consumption WHERE article_nr = ?", (art_nr,))
                
                    # Ð£Ð´Ð°Ð»ÑÐµÐ¼ ÑÐ°Ð¼ Ñ€ÐµÑ†ÐµÐ¿Ñ‚
                    cursor.execute("DELETE FROM recipes WHERE article_nr = ?", (art_nr,))
                
                    if cursor.rowcount > 0:
                        deleted = True
                        logger.info(f"âœ… Ð£Ð¡ÐŸÐ•Ð¨ÐÐž Ð£Ð”ÐÐ›Ð•Ð: {art_nr}")
                        break # Ð’Ñ‹Ñ…Ð¾Ð´Ð¸Ð¼, ÐµÑÐ»Ð¸ ÑƒÐ´Ð°Ð»Ð¸Ð»Ð¸

            conn.commit()

            if deleted:
                await websocket.send(json.dumps({'type': 'success', 'message': f'Ð ÐµÑ†ÐµÐ¿Ñ‚ ÑƒÐ´Ð°Ð»Ñ‘Ð½'}))
                # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ ÑÐ¿Ð¸ÑÐ¾Ðº
                await self.handle_get_recipes(websocket)
            else:
                logger.warning(f"âš ï¸ Ð ÐµÑ†ÐµÐ¿Ñ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½ ÑÑ€ÐµÐ´Ð¸ ÐºÐ°Ð½Ð´Ð¸Ð´Ð°Ñ‚Ð¾Ð²: {candidates}")
                await websocket.send(json.dumps({'type': 'error', 'message': f'Ð ÐµÑ†ÐµÐ¿Ñ‚ {original_art} Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½ Ð² Ð±Ð°Ð·Ðµ'}))

        except Exception as e:
            logger.error(f"Error deleting recipe: {e}")
            import traceback; traceback.print_exc()
            await websocket.send(json.dumps({'type': 'error', 'message': f'ÐžÑˆÐ¸Ð±ÐºÐ°: {str(e)}'}))
        finally:
            conn.close()

    async def handle_save_recipe_extended(self, websocket, data):
        """
        Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ñ€Ð°ÑÑˆÐ¸Ñ€ÐµÐ½Ð½Ñ‹Ð¹ Ñ€ÐµÑ†ÐµÐ¿Ñ‚.
        Ð˜Ð¡ÐŸÐ ÐÐ’Ð›Ð•ÐÐž: Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÑ‚ÑÑ Ð¿Ñ€Ð°Ð²Ð¸Ð»ÑŒÐ½Ð¾Ðµ Ð¸Ð¼Ñ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ parent_article_nr Ð´Ð»Ñ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ð¾Ð².
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            article_nr = self._resolve_recipe_article_nr_for_write(cursor, data.get('article_nr'))
            if not article_nr:
                await websocket.send(json.dumps({'type': 'error', 'message': 'ÐŸÑƒÑÑ‚Ð¾Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»'}))
                return

            name = data['name']
            category = data['category']
            composition = data.get('composition', [])
            comments = data.get('comments', '')
            items_per_tray = data.get('items_per_tray', 1.0)
            min_batch_size = data.get('min_batch_size', 1)
            min_stock_level = data.get('min_stock_level', 0)
            unit_price = float(data.get('unit_price', 0.0))
            dough_id = data.get('dough_id')
            active = data.get('active', 1)
            freeze_mode = str(data.get('freeze_mode', '') or '')

            composition_json = json.dumps(composition, ensure_ascii=False)

            # 1. ÐžÐ‘ÐÐžÐ’Ð›Ð•ÐÐ˜Ð• Ð¢ÐÐ‘Ð›Ð˜Ð¦Ð« RECIPES
            cursor.execute("SELECT 1 FROM recipes WHERE article_nr = ?", (article_nr,))
            if cursor.fetchone():
                cursor.execute('''
                    UPDATE recipes
                    SET name=?, category=?, dough_id=?, items_per_tray=?, min_batch_size=?, min_stock_level=?,
                        unit_price=?, composition=?, comments=?, active=?, freeze_mode=?, updated_at=?
                    WHERE article_nr=?
                ''', (name, category, dough_id, items_per_tray, min_batch_size, min_stock_level,
                      unit_price, composition_json, comments, active, freeze_mode, datetime.now().isoformat(), article_nr))
            else:
                cursor.execute('''
                    INSERT INTO recipes
                    (article_nr, name, category, dough_id, items_per_tray, min_batch_size, min_stock_level, unit_price, composition, comments, active, freeze_mode, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (article_nr, name, category, dough_id, items_per_tray, min_batch_size, min_stock_level,
                      unit_price, composition_json, comments, active, freeze_mode, datetime.now().isoformat()))

            # 2. ÐžÐ‘ÐÐžÐ’Ð›Ð•ÐÐ˜Ð• Ð¡ÐžÐ¡Ð¢ÐÐ’Ð (BOM) - Ð˜Ð¡ÐŸÐ ÐÐ’Ð›Ð•ÐÐ ÐžÐ¨Ð˜Ð‘ÐšÐ ÐšÐžÐ›ÐžÐÐšÐ˜
            # Ð£Ð´Ð°Ð»ÑÐµÐ¼ ÑÑ‚Ð°Ñ€Ñ‹Ðµ (Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ parent_article_nr)
            cursor.execute('DELETE FROM recipe_components WHERE parent_article_nr = ?', (article_nr,))

            # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ðµ
            for comp in composition:
                comp_name = comp.get('component', '')
                quantity = float(comp.get('quantity', 0))
                unit = comp.get('unit', 'ÑˆÑ‚')

                # ÐÐ°Ð¹Ñ‚Ð¸ ID ÐºÐ¾Ð¼Ð¿Ð¾Ð½ÐµÐ½Ñ‚Ð°
                cursor.execute("SELECT dough_id FROM dough_types WHERE name = ?", (comp_name,))
                comp_row = cursor.fetchone()
                comp_id = comp_row[0] if comp_row else comp_name.lower().replace(' ', '_')

                # Ð’ÑÑ‚Ð°Ð²Ð»ÑÐµÐ¼ Ñ Ð¿Ñ€Ð°Ð²Ð¸Ð»ÑŒÐ½Ñ‹Ð¼ Ð¸Ð¼ÐµÐ½ÐµÐ¼ ÐºÐ¾Ð»Ð¾Ð½ÐºÐ¸ parent_article_nr
                cursor.execute('''
                    INSERT INTO recipe_components (parent_article_nr, component_id, component_name, quantity, unit)
                    VALUES (?, ?, ?, ?, ?)
                ''', (article_nr, comp_id, comp_name, quantity, unit))

            # 3. ÐžÐ‘ÐÐžÐ’Ð›Ð•ÐÐ˜Ð• ÐŸÐžÐ¢Ð Ð•Ð‘Ð›Ð•ÐÐ˜Ð¯ Ð Ð•Ð¡Ð£Ð Ð¡ÐžÐ’
            resource_consumption = data.get('resource_consumption', [])
            if resource_consumption:
                cursor.execute('DELETE FROM product_resource_consumption WHERE article_nr = ?', (article_nr,))
                for rc in resource_consumption:
                    cursor.execute('''
                        INSERT INTO product_resource_consumption
                        (article_nr, resource_id, time_needed_min, comments, created_at, updated_at)
                        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
                    ''', (article_nr, int(rc['resource_id']), float(rc['time_needed_min']), rc.get('comments', '')))

            conn.commit()
            logger.info(f"Recipe saved: {article_nr} - {name}")

            await self.handle_get_recipes(websocket)
            await websocket.send(json.dumps({'type': 'success', 'message': f'Ð ÐµÑ†ÐµÐ¿Ñ‚ "{name}" ÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½'}))

        except Exception as e:
            logger.error(f"Error saving recipe: {e}")
            import traceback; traceback.print_exc()
            await websocket.send(json.dumps({'type': 'error', 'message': f'ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ: {str(e)}'}))
        finally:
            conn.close()

    async def handle_import_recipes_from_orders(self, websocket):
        """ÐŸÑ€Ð¾Ð¹Ñ‚Ð¸ÑÑŒ Ð¿Ð¾ Ð²ÑÐµÐ¼ Ð·Ð°ÐºÐ°Ð·Ð°Ð¼ Ð¸ Ð´Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð½Ð¾Ð²Ñ‹Ðµ Ñ‚Ð¾Ð²Ð°Ñ€Ñ‹ Ð² Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð²"""
        orders = self.db.get_all_orders()
        added_count = 0

        with self.db.safe_connection() as conn:
            cursor = conn.cursor()

            for order in orders:
                # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ ÑÐ¿Ð¸ÑÐ¾Ðº Ñ‚Ð¾Ð²Ð°Ñ€Ð¾Ð² Ð¸Ð· JSON Ð·Ð°ÐºÐ°Ð·Ð°
                artikel_list = order['data'].get('artikel', [])
                for art in artikel_list:
                    art_nr = str(art.get('nummer', art.get('artikel_nr', ''))).strip()
                    name = str(art.get('beschreibung', art.get('name', ''))).strip()

                    if not art_nr: continue
                    if art_nr.isdigit():
                        art_nr = art_nr.zfill(5)

                    # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼, ÐµÑÑ‚ÑŒ Ð»Ð¸ ÑƒÐ¶Ðµ Ñ‚Ð°ÐºÐ¾Ð¹ Ñ€ÐµÑ†ÐµÐ¿Ñ‚
                    cursor.execute("SELECT 1 FROM recipes WHERE article_nr = ?", (art_nr,))
                    if not cursor.fetchone():
                        # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ "Ð¿ÑƒÑÑ‚Ñ‹ÑˆÐºÑƒ" Ñ Ð¼ÐµÑ‚ÐºÐ¾Ð¹ NEW, ÐºÐ¾Ñ‚Ð¾Ñ€ÑƒÑŽ Ð°Ð´Ð¼Ð¸Ð½ Ð¿Ð¾Ñ‚Ð¾Ð¼ Ð·Ð°Ð¿Ð¾Ð»Ð½Ð¸Ñ‚
                        cursor.execute('''
                            INSERT INTO recipes (article_nr, name, dough_id, items_per_tray, is_new, updated_at)
                            VALUES (?, ?, 'unknown', 1.0, 1, ?)
                        ''', (art_nr, name, datetime.now().isoformat()))
                        added_count += 1

            conn.commit()

        logger.info(f"Imported {added_count} new recipes from order history")

        # Ð¡Ñ€Ð°Ð·Ñƒ Ð¾Ð±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ ÑÐºÑ€Ð°Ð½ Ð°Ð´Ð¼Ð¸Ð½Ð°
        await self.handle_get_recipes(websocket)

    async def handle_toggle_recipe_active(self, websocket, data):
        """Ð’ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ/Ð²Ñ‹ÐºÐ»ÑŽÑ‡Ð¸Ñ‚ÑŒ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» (active = 1/0)"""
        article_nr = str(data.get('article_nr', '')).strip()
        try:
            with self.db.safe_connection() as conn:
                cursor = conn.cursor()
                # Ð¢Ð¾Ñ‡Ð½Ñ‹Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» Ð¿Ñ€Ð¸Ð¾Ñ€Ð¸Ñ‚ÐµÑ‚Ð½ÐµÐµ (Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð½Ðµ Ð¿ÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ð°Ñ‚ÑŒ Ñ‡ÑƒÐ¶Ð¾Ð¹ Ð´ÑƒÐ±Ð»ÑŒ).
                cursor.execute("SELECT 1 FROM recipes WHERE article_nr = ?", (article_nr,))
                exists_exact = cursor.fetchone()
                if not exists_exact and article_nr.isdigit():
                    article_nr = article_nr.zfill(5)
                # Legacy-Ð´ÑƒÐ±Ð»Ð¸ Ð±ÐµÐ· Ð²ÐµÐ´ÑƒÑ‰ÐµÐ³Ð¾ Ð½ÑƒÐ»Ñ Ð½ÐµÐ»ÑŒÐ·Ñ Ð²ÐºÐ»ÑŽÑ‡Ð°Ñ‚ÑŒ, ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ ÐºÐ°Ð½Ð¾Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ».
                if article_nr.isdigit() and len(article_nr) < 5:
                    canon = article_nr.zfill(5)
                    cursor.execute("SELECT 1 FROM recipes WHERE article_nr = ?", (canon,))
                    has_canon = cursor.fetchone()
                    if has_canon:
                        cursor.execute(
                            "UPDATE recipes SET active = 0, updated_at = ? WHERE article_nr = ?",
                            (datetime.now().isoformat(), article_nr)
                        )
                    else:
                        cursor.execute(
                            "UPDATE recipes SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END, updated_at = ? WHERE article_nr = ?",
                            (datetime.now().isoformat(), article_nr)
                        )
                else:
                    # ÐŸÐµÑ€ÐµÐºÐ»ÑŽÑ‡Ð°ÐµÐ¼: ÐµÑÐ»Ð¸ Ð±Ñ‹Ð»Ð¾ 1 â€” ÑÑ‚Ð°Ð½ÐµÑ‚ 0, ÐµÑÐ»Ð¸ 0 â€” ÑÑ‚Ð°Ð½ÐµÑ‚ 1
                    cursor.execute(
                        "UPDATE recipes SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END, updated_at = ? WHERE article_nr = ?",
                        (datetime.now().isoformat(), article_nr)
                    )
                conn.commit()
                new_active = cursor.execute("SELECT active FROM recipes WHERE article_nr = ?", (article_nr,)).fetchone()
            status = "Ð²ÐºÐ»ÑŽÑ‡Ñ‘Ð½" if (new_active and new_active[0] == 1) else "Ð²Ñ‹ÐºÐ»ÑŽÑ‡ÐµÐ½"
            logger.info(f"Recipe {article_nr} toggled: {status}")
            # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ ÑÐ¿Ð¸ÑÐ¾Ðº Ñƒ Ð²ÑÐµÑ… Ð°Ð´Ð¼Ð¸Ð½Ð¾Ð²
            await self.handle_get_recipes(websocket)
        except Exception as e:
            logger.error(f"Toggle recipe active error: {e}")

    def auto_add_new_articles_from_order(self, artikel_list: list) -> int:
        """
        ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÑ‚ Ð½Ð¾Ð²Ñ‹Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñ‹ Ð¸Ð· Ð·Ð°ÐºÐ°Ð·Ð° Ð² Ð±Ð°Ð·Ñƒ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² Ð¸ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸.
        Ð’Ñ‹Ð·Ñ‹Ð²Ð°ÐµÑ‚ÑÑ Ð¿Ñ€Ð¸ ÑÐ¾Ð·Ð´Ð°Ð½Ð¸Ð¸ ÐºÐ°Ð¶Ð´Ð¾Ð³Ð¾ Ð½Ð¾Ð²Ð¾Ð³Ð¾ Ð·Ð°ÐºÐ°Ð·Ð°.

        Args:
            artikel_list: Ð¡Ð¿Ð¸ÑÐ¾Ðº Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Ð¸Ð· Ð·Ð°ÐºÐ°Ð·Ð°

        Returns:
            ÐšÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð½Ñ‹Ñ… Ð½Ð¾Ð²Ñ‹Ñ… Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð²
        """
        if not artikel_list:
            return 0

        added_count = 0
        today = datetime.now().strftime('%Y-%m-%d')

        try:
            with self.db.safe_connection() as conn:
                cursor = conn.cursor()

                for art in artikel_list:
                    # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð½Ð¾Ð¼ÐµÑ€ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð° (Ð¼Ð¾Ð¶ÐµÑ‚ Ð±Ñ‹Ñ‚ÑŒ Ð² Ñ€Ð°Ð·Ð½Ñ‹Ñ… Ð¿Ð¾Ð»ÑÑ…)
                    art_nr = str(art.get('nummer', art.get('artikel_nr', art.get('artikelnr', '')))).strip()
                    name = str(art.get('beschreibung', art.get('name', art.get('bezeichnung', '')))).strip()

                    if not art_nr:
                        continue

                    # ÐÐ¾Ñ€Ð¼Ð°Ð»Ð¸Ð·ÑƒÐµÐ¼ Ð½Ð¾Ð¼ÐµÑ€ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð° (Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð²ÐµÐ´ÑƒÑ‰Ð¸Ðµ Ð½ÑƒÐ»Ð¸ Ð´Ð¾ 5 ÑÐ¸Ð¼Ð²Ð¾Ð»Ð¾Ð²)
                    if art_nr.isdigit() and len(art_nr) < 5:
                        art_nr = art_nr.zfill(5)

                    # 1. ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼, ÐµÑÑ‚ÑŒ Ð»Ð¸ ÑƒÐ¶Ðµ Ñ‚Ð°ÐºÐ¾Ð¹ Ñ€ÐµÑ†ÐµÐ¿Ñ‚
                    cursor.execute("SELECT 1 FROM recipes WHERE article_nr = ?", (art_nr,))
                    if not cursor.fetchone():
                        # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ð¹ Ñ€ÐµÑ†ÐµÐ¿Ñ‚ Ñ Ð¼ÐµÑ‚ÐºÐ¾Ð¹ is_new=1
                        cursor.execute('''
                            INSERT INTO recipes (article_nr, name, dough_id, items_per_tray, is_new, updated_at)
                            VALUES (?, ?, 'unknown', 1.0, 1, ?)
                        ''', (art_nr, name or f'ÐÐ¾Ð²Ñ‹Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» {art_nr}', datetime.now().isoformat()))
                        added_count += 1
                        logger.info(f"ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½ Ð½Ð¾Ð²Ñ‹Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» Ð² Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ñ‹: {art_nr} - {name}")

                        # 2. Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð·Ð°Ð¿Ð¸ÑÑŒ Ð² daily_stock_reports Ñ Ð½ÑƒÐ»ÐµÐ²Ñ‹Ð¼ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾Ð¼
                        cursor.execute('''
                            INSERT OR IGNORE INTO daily_stock_reports (date, article_nr, quantity, created_at, updated_at)
                            VALUES (?, ?, 0, ?, ?)
                        ''', (today, art_nr, datetime.now().isoformat(), datetime.now().isoformat()))

                conn.commit()

            if added_count > 0:
                logger.info(f"ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¾ {added_count} Ð½Ð¾Ð²Ñ‹Ñ… Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Ð¸Ð· Ð·Ð°ÐºÐ°Ð·Ð°")

        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¿Ñ€Ð¸ Ð°Ð²Ñ‚Ð¾Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¸Ð¸ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð²: {e}")
            import traceback
            traceback.print_exc()

        return added_count

    # ============================================
    # ÐžÐ‘Ð ÐÐ‘ÐžÐ¢Ð§Ð˜ÐšÐ˜ ÐŸÐ ÐÐ’Ð˜Ð› ÐŸÐ ÐžÐ˜Ð—Ð’ÐžÐ”Ð¡Ð¢Ð’Ð
    # ============================================
    async def handle_get_production_rules(self, websocket):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð° Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð°"""
        with self.db.safe_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT category, days_offset, updated_at FROM production_rules ORDER BY category")
            rules = []

            for row in cursor.fetchall():
                try:
                    days_offset = json.loads(row['days_offset'])
                except:
                    days_offset = {}

                rules.append({
                    'category': row['category'],
                    'days_offset': days_offset,
                    'updated_at': row['updated_at']
                })

        await websocket.send(json.dumps({
            'type': 'production_rules_data',
            'rules': rules
        }))

        logger.info(f"Sent {len(rules)} production rules")

    async def handle_get_production_rule(self, websocket, data):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¾Ð´Ð½Ð¾ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð¾"""
        category = data['category']

        with self.db.safe_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT days_offset FROM production_rules WHERE category = ?", (category,))
            row = cursor.fetchone()

        if row:
            try:
                days_offset = json.loads(row['days_offset'])
            except:
                days_offset = {}

            await websocket.send(json.dumps({
                'type': 'production_rule_detail',
                'category': category,
                'days_offset': days_offset
            }))

            logger.info(f"Sent production rule details for: {category}")

    async def handle_save_production_rule(self, websocket, data):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð¾ Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð°"""
        category = data['category']
        days_offset = data['days_offset']  # dict: {-1: 0.5, -2: 0.5}

        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # ÐšÐ¾Ð½Ð²ÐµÑ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ Ð² JSON string
            days_offset_json = json.dumps(days_offset)

            # UPSERT
            cursor.execute('''
                INSERT OR REPLACE INTO production_rules (category, days_offset, updated_at)
                VALUES (?, ?, ?)
            ''', (category, days_offset_json, datetime.now().isoformat()))

            conn.commit()
            logger.info(f"Saved production rule: {category} = {days_offset}")

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ñ‹Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº
            await self.handle_get_production_rules(websocket)

        except Exception as e:
            logger.error(f"Error saving production rule: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ñ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð°: {str(e)}'
            }))
        finally:
            conn.close()

    async def handle_delete_production_rule(self, websocket, data):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð¾ Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð°"""
        category = data['category']

        # ÐÐµÐ»ÑŒÐ·Ñ ÑƒÐ´Ð°Ð»Ð¸Ñ‚ÑŒ 'default'
        if category == 'default':
            await websocket.send(json.dumps({
                'type': 'error',
                'message': 'ÐÐµÐ»ÑŒÐ·Ñ ÑƒÐ´Ð°Ð»Ð¸Ñ‚ÑŒ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð¾ Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ'
            }))
            return

        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM production_rules WHERE category = ?", (category,))
            conn.commit()

            logger.info(f"Deleted production rule: {category}")

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð¾Ð±Ð½Ð¾Ð²Ð»Ñ‘Ð½Ð½Ñ‹Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº
            await self.handle_get_production_rules(websocket)

        except Exception as e:
            logger.error(f"Error deleting production rule: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'ÐžÑˆÐ¸Ð±ÐºÐ° ÑƒÐ´Ð°Ð»ÐµÐ½Ð¸Ñ Ð¿Ñ€Ð°Ð²Ð¸Ð»Ð°: {str(e)}'
            }))
        finally:
            conn.close()

    async def send_json(self, websocket, data):
        """Ð’ÑÐ¿Ð¾Ð¼Ð¾Ð³Ð°Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ð¹ Ð¼ÐµÑ‚Ð¾Ð´ Ð´Ð»Ñ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÐºÐ¸ JSON Ñ Ð¿Ð¾Ð´Ð´ÐµÑ€Ð¶ÐºÐ¾Ð¹ Ð´Ð°Ñ‚"""
        try:
            # default=str Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ Ð¿Ñ€ÐµÐ²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ datetime Ð² ÑÑ‚Ñ€Ð¾ÐºÐ¸
            await websocket.send(json.dumps(data, default=str))
        except Exception as e:
            logger.error(f"Error sending JSON: {e}")

    async def send_error(self, websocket, message):
        """Ð’ÑÐ¿Ð¾Ð¼Ð¾Ð³Ð°Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ð¹ Ð¼ÐµÑ‚Ð¾Ð´ Ð´Ð»Ñ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²ÐºÐ¸ Ð¾ÑˆÐ¸Ð±Ð¾Ðº"""
        await self.send_json(websocket, {
            'type': 'error', 
            'message': message
        })
        

    async def send_initial_data(self, websocket, user):
        """
        ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð½Ð°Ñ‡Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¿Ð¾ÑÐ»Ðµ Ð°Ð²Ñ‚Ð¾Ñ€Ð¸Ð·Ð°Ñ†Ð¸Ð¸.
        ÐŸÐžÐ›ÐÐÐ¯ Ð’Ð•Ð Ð¡Ð˜Ð¯: Ð¡ Ñ€Ð°ÑÑ‡ÐµÑ‚Ð¾Ð¼ Ñ†ÐµÐ½, Ð°Ð´Ð¼Ð¸Ð½ÐºÐ¾Ð¹ Ð¸ Ð·Ð°Ñ‰Ð¸Ñ‚Ð¾Ð¹ Ð¾Ñ‚ Ð·Ð°Ð²Ð¸ÑÐ°Ð½Ð¸Ñ.
        """
        try:
            logger.info(f"Preparing initial data for {user.username}...")

            # --- 1. Ð—ÐÐ“Ð Ð£Ð—ÐšÐ ÐžÐ¡ÐÐžÐ’ÐÐ«Ð¥ Ð”ÐÐÐÐ«Ð¥ (ÐÐ¡Ð˜ÐÐ¥Ð ÐžÐÐÐž) ---
            # Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ _run_sync, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ñ‡Ñ‚ÐµÐ½Ð¸Ðµ Ñ Ð´Ð¸ÑÐºÐ° Ð½Ðµ Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ð»Ð¾ Ð´Ñ€ÑƒÐ³Ð¸Ñ… Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¹
            # Перед выдачей данных синхронизируем маршруты заказов с актуальной логистикой клиентов.
            try:
                await self._run_sync(self.db.sync_all_orders_routes_from_clients)
            except Exception as sync_exc:
                logger.warning(f"Route sync before initial_data failed: {sync_exc}")
            
            # Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ð·Ð°ÐºÐ°Ð·Ñ‹
            orders = await self._run_sync(self.db.get_all_orders)
            
            # Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ð»Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÑƒ (Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ñ‹ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²) - ÑÑ‚Ð¾ Ð²Ð°Ð¶Ð½Ð¾ Ð´Ð»Ñ ÐºÐ°Ñ€Ñ‚Ñ‹ Ð¸ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹!
            logistics = await self._run_sync(self.db.get_all_logistics)

            # Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ñ‹ Ð´Ð»Ñ Ñ€Ð°ÑÑ‡ÐµÑ‚Ð° Ñ†ÐµÐ½ (Ð²Ð¼ÐµÑÑ‚Ð¾ _get_recipe_prices_cache)
            recipes = await self._run_sync(self.db.get_all_recipes)

            # --- 2. Ð ÐÐ¡Ð§Ð•Ð¢ Ð¦Ð•Ð (TOTAL VALUE) ---
            # Ð­Ñ‚Ð¾ Ð´ÐµÐ»Ð°ÐµÑ‚ÑÑ Ð² Ð¿Ð°Ð¼ÑÑ‚Ð¸, Ð±Ñ‹ÑÑ‚Ñ€Ð¾, Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²ÐºÐ° Ð½Ðµ ÑÑ‚Ñ€Ð°ÑˆÐ½Ð°
            try:
                # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ Ð±Ñ‹ÑÑ‚Ñ€Ñ‹Ð¹ ÑÐ»Ð¾Ð²Ð°Ñ€ÑŒ Ñ†ÐµÐ½: { '05001': 12.50, ... }
                recipe_prices = {}
                if recipes:
                    for r in recipes:
                        # ÐÐ¾Ñ€Ð¼Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ñ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð° (ÑƒÐ±Ð¸Ñ€Ð°ÐµÐ¼ Ð¿Ñ€Ð¾Ð±ÐµÐ»Ñ‹, Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð½ÑƒÐ»Ð¸)
                        art = str(r['article_nr']).strip()
                        if art.isdigit(): art = art.zfill(5)
                        
                        # Ð¦ÐµÐ½Ð° Ð·Ð° ÑˆÑ‚ÑƒÐºÑƒ (unit_price) Ð¸Ð»Ð¸ Ð²Ñ‹Ñ‡Ð¸ÑÐ»ÑÐµÐ¼ ÐºÐ°Ðº-Ñ‚Ð¾ Ð¸Ð½Ð°Ñ‡Ðµ
                        # Ð•ÑÐ»Ð¸ Ð² recipes ÐµÑÑ‚ÑŒ Ð¿Ð¾Ð»Ðµ unit_price, Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ ÐµÐ³Ð¾
                        price = float(r.get('unit_price', 0.0) or 0.0)
                        if price > 0:
                            recipe_prices[art] = price

                # ÐŸÑ€Ð¾Ñ…Ð¾Ð´Ð¸Ð¼ Ð¿Ð¾ Ð·Ð°ÐºÐ°Ð·Ð°Ð¼ Ð¸ ÑÑ‡Ð¸Ñ‚Ð°ÐµÐ¼ ÑÑƒÐ¼Ð¼Ñƒ, ÐµÑÐ»Ð¸ Ð¾Ð½Ð° 0
                if recipe_prices:
                    for order in orders:
                        # Ð•ÑÐ»Ð¸ ÑÑƒÐ¼Ð¼Ð° ÑƒÐ¶Ðµ ÐµÑÑ‚ÑŒ, Ð¿Ñ€Ð¾Ð¿ÑƒÑÐºÐ°ÐµÐ¼
                        if order.get('total_value', 0) > 0:
                            continue
                            
                        # Ð¡Ñ‡Ð¸Ñ‚Ð°ÐµÐ¼ ÑÑƒÐ¼Ð¼Ñƒ Ð¿Ð¾ Ð¿Ð¾Ð·Ð¸Ñ†Ð¸ÑÐ¼
                        artikel = order.get('artikel', [])
                        if not artikel: continue
                        
                        calc_total = 0.0
                        for art in artikel:
                            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» Ð¸Ð· Ð¿Ð¾Ð·Ð¸Ñ†Ð¸Ð¸
                            art_nr = str(art.get('artikel_nr') or art.get('nummer', '')).strip()
                            if art_nr.isdigit(): art_nr = art_nr.zfill(5)
                            
                            qty = float(art.get('menge', 0) or 0)
                            
                            # Ð‘ÐµÑ€ÐµÐ¼ Ñ†ÐµÐ½Ñƒ Ð¸Ð· ÑÐ¿Ñ€Ð°Ð²Ð¾Ñ‡Ð½Ð¸ÐºÐ°
                            price = recipe_prices.get(art_nr, 0.0)
                            calc_total += qty * price
                        
                        if calc_total > 0:
                            order['total_value'] = round(calc_total, 2)
                            
            except Exception as e:
                logger.warning(f"Error calculating order totals: {e}")

            # --- 3. ÐžÐ¢ÐŸÐ ÐÐ’ÐšÐ ÐžÐ¡ÐÐžÐ’ÐÐžÐ“Ðž ÐŸÐÐšÐ•Ð¢Ð ---
            if websocket.closed: return

            initial_response = {
                'type': 'initial_data',
                'orders': orders,
                'logistics': logistics, # Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¾, Ñ‡Ñ‚Ð¾Ð±Ñ‹ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ñ‹ Ð²Ð¸Ð´ÐµÐ»Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ñ‹
                'user': {
                    'username': user.username,
                    'first_name': getattr(user, 'first_name', ''),
                    'last_name': getattr(user, 'last_name', ''),
                    'display_name': getattr(user, 'display_name', user.username),
                    'role': user.role,
                    'warehouse_id': user.warehouse_id,
                    'permissions': user.permissions
                }
            }
            
            await self.send_json(websocket, initial_response)
            logger.info(f"âœ… Initial data sent to {user.username} ({len(orders)} orders)")

            # --- 4. ÐŸÐ ÐžÐ’Ð•Ð ÐšÐ ÐŸÐ ÐÐ’ (ADMIN) ---
            user_perms = [p.strip() for p in (user.permissions or '').split(',') if p.strip()]
            is_admin = user.role == 'admin' or 'admin' in user_perms

            # --- 5. ÐžÐ¢ÐŸÐ ÐÐ’ÐšÐ Ð”ÐÐÐÐ«Ð¥ ÐÐ”ÐœÐ˜ÐÐ˜Ð¡Ð¢Ð ÐÐ¢ÐžÐ Ð ---
            if is_admin:
                # Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÐ¼ ÐºÐ°Ð¶Ð´ÑƒÑŽ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾ Ñ‡ÐµÑ€ÐµÐ· _run_sync
                # Ð•ÑÐ»Ð¸ Ð¾Ð´Ð½Ð° Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° ÑƒÐ¿Ð°Ð´ÐµÑ‚, Ð¾ÑÑ‚Ð°Ð»ÑŒÐ½Ñ‹Ðµ Ð·Ð°Ð³Ñ€ÑƒÐ·ÑÑ‚ÑÑ
                
                users_list = []
                try:
                    users_list = await self._run_sync(self.db.get_all_users)
                except Exception as e: logger.error(f"Failed to load users: {e}")

                errors_list = []
                try:
                    errors_list = await self._run_sync(self.db.get_errors, 100)
                except Exception as e: logger.error(f"Failed to load errors: {e}")

                logs_list = []
                try:
                    logs_list = await self._run_sync(self.db.get_logs, 200)
                except Exception as e: logger.error(f"Failed to load logs: {e}")

                cond_articles = []
                try:
                    cond_articles = await self._run_sync(self.db.get_conditional_articles)
                except Exception as e: logger.error(f"Failed to load conditional articles: {e}")
                
                categories = []
                try:
                    categories = await self._run_sync(self.db.get_all_categories)
                except Exception as e: logger.error(f"Failed to load categories: {e}")

                if not websocket.closed:
                    await self.send_json(websocket, {
                        'type': 'admin_data',
                        'users': users_list,
                        'errors': errors_list,
                        'logs': logs_list,
                        'conditional_articles': cond_articles,
                        'categories': categories
                    })
                    logger.info(f"âœ… Admin data sent to {user.username}")

            # --- 6. ÐžÐ¢ÐŸÐ ÐÐ’ÐšÐ Ð£Ð¡Ð›ÐžÐ’ÐÐ«Ð¥ ÐÐ Ð¢Ð˜ÐšÐ£Ð›ÐžÐ’ (Ð”Ð›Ð¯ ÐžÐ‘Ð«Ð§ÐÐ«Ð¥ Ð®Ð—Ð•Ð ÐžÐ’) ---
            elif not is_admin:
                # ÐžÐ±Ñ‹Ñ‡Ð½Ñ‹Ð¼ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑÐ¼ Ñ‚Ð¾Ð¶Ðµ Ð½ÑƒÐ¶Ð½Ð¾ Ð·Ð½Ð°Ñ‚ÑŒ ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñ‹ (Ñ‡Ñ‚Ð¾Ð±Ñ‹ ÑÐºÑ€Ñ‹Ð²Ð°Ñ‚ÑŒ Ð»Ð¸ÑˆÐ½ÐµÐµ)
                try:
                    cond_articles = await self._run_sync(self.db.get_conditional_articles)
                    if not websocket.closed:
                        await self.send_json(websocket, {
                            'type': 'conditional_articles',
                            'articles': cond_articles
                        })
                except Exception as e:
                    logger.warning(f"Failed to send conditional articles to user: {e}")

        except Exception as e:
            logger.error(f"CRITICAL ERROR in send_initial_data: {e}", exc_info=True)
            # ÐŸÑ‹Ñ‚Ð°ÐµÐ¼ÑÑ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ñ…Ð¾Ñ‚ÑŒ Ñ‡Ñ‚Ð¾-Ñ‚Ð¾, Ñ‡Ñ‚Ð¾Ð±Ñ‹ ÐºÐ»Ð¸ÐµÐ½Ñ‚ Ð¿ÐµÑ€ÐµÑÑ‚Ð°Ð» ÐºÑ€ÑƒÑ‚Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸Ð½Ð½ÐµÑ€
            try:
                if not websocket.closed:
                    await self.send_error(websocket, "ÐžÑˆÐ¸Ð±ÐºÐ° Ð·Ð°Ð³Ñ€ÑƒÐ·ÐºÐ¸ Ð´Ð°Ð½Ð½Ñ‹Ñ…. ÐŸÐ¾Ð¿Ñ€Ð¾Ð±ÑƒÐ¹Ñ‚Ðµ Ð¾Ð±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ.")
            except: pass

    def _get_comm_bootstrap_for_user(self, user_id: int, role: str) -> dict:
        dialogs = self.db.get_comm_dialogs_for_user(int(user_id))
        users = self.db.get_comm_users()
        tasks = self.db.get_comm_tasks_for_user(int(user_id), str(role))
        return {
            'users': users,
            'dialogs': dialogs,
            'tasks': tasks
        }

    async def _broadcast_to_user_ids(self, user_ids: list, message: dict):
        if not user_ids:
            return
        targets = []
        uid_set = {int(u) for u in user_ids if str(u).strip().isdigit()}
        for s in self.sessions.sessions.values():
            if int(s.user_id) in uid_set:
                targets.append(s.websocket)
        if not targets:
            return
        payload = json.dumps(message)
        await asyncio.gather(*[ws.send(payload) for ws in targets], return_exceptions=True)

    async def handle_get_comm_bootstrap(self, websocket, session):
        try:
            data = await asyncio.wait_for(
                self._run_sync(self._get_comm_bootstrap_for_user, session.user_id, session.role),
                timeout=20
            )
            await self.send_json(websocket, {'type': 'comm_bootstrap', **data})
        except asyncio.TimeoutError:
            logger.error(f"COMM bootstrap timeout for user_id={session.user_id}")
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'Users list loading timeout'})

    async def handle_create_comm_dialog(self, websocket, session, data):
        payload = data.get('dialog') or {}
        title = str(payload.get('title') or '').strip()
        participant_ids = payload.get('participant_ids') or []
        is_group = bool(payload.get('is_group', False))
        if not participant_ids:
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'Select at least one participant'})
            return
        dialog_id = await self._run_sync(self.db.create_comm_dialog, session.user_id, title or 'Dialog', participant_ids, is_group)
        member_ids = await self._run_sync(self.db.get_comm_dialog_members, dialog_id)
        user_dialogs = await self._run_sync(self.db.get_comm_dialogs_for_user, session.user_id)
        dialog_obj = next((d for d in user_dialogs if int(d.get('dialog_id', 0)) == int(dialog_id)), None)
        await self._broadcast_to_user_ids(member_ids, {'type': 'comm_dialog_created', 'dialog': dialog_obj})

    async def handle_add_comm_dialog_participants(self, websocket, session, data):
        dialog_id = int(data.get('dialog_id') or 0)
        participant_ids = data.get('participant_ids') or []
        if dialog_id <= 0 or not participant_ids:
            return
        if not await self._run_sync(self.db.is_comm_dialog_member, dialog_id, session.user_id):
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'No access to this dialog'})
            return
        await self._run_sync(self.db.add_comm_dialog_participants, dialog_id, participant_ids)
        member_ids = await self._run_sync(self.db.get_comm_dialog_members, dialog_id)
        await self._broadcast_to_user_ids(member_ids, {'type': 'comm_dialog_updated', 'dialog_id': dialog_id})

    async def handle_get_comm_messages(self, websocket, session, data):
        dialog_id = int(data.get('dialog_id') or 0)
        limit = int(data.get('limit') or 120)
        before_message_id = int(data.get('before_message_id') or 0)
        mode = str(data.get('mode') or 'replace')
        if limit <= 0:
            limit = 120
        if limit > 300:
            limit = 300
        if dialog_id <= 0:
            return
        if not await self._run_sync(self.db.is_comm_dialog_member, dialog_id, session.user_id):
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'No access to this dialog'})
            return
        if mode != 'prepend':
            await self._run_sync(self.db.mark_comm_dialog_read, dialog_id, session.user_id)
        msgs = await self._run_sync(self.db.get_comm_messages, dialog_id, limit, session.user_id, before_message_id)
        await self.send_json(websocket, {
            'type': 'comm_messages',
            'dialog_id': dialog_id,
            'messages': msgs,
            'mode': mode
        })

    async def handle_get_comm_dialog_members(self, websocket, session, data):
        dialog_id = int(data.get('dialog_id') or 0)
        if dialog_id <= 0:
            return
        if not await self._run_sync(self.db.is_comm_dialog_member, dialog_id, session.user_id):
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'No access to this dialog'})
            return
        members = await self._run_sync(self.db.get_comm_dialog_members_info, dialog_id)
        await self.send_json(websocket, {'type': 'comm_dialog_members', 'dialog_id': dialog_id, 'members': members})

    async def handle_send_comm_message(self, websocket, session, data):
        dialog_id = int(data.get('dialog_id') or 0)
        text = str(data.get('text') or '').strip()
        if dialog_id <= 0 or not text:
            return
        if not await self._run_sync(self.db.is_comm_dialog_member, dialog_id, session.user_id):
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'No access to this dialog'})
            return
        msg_obj = await self._run_sync(self.db.create_comm_message, dialog_id, session.user_id, text)
        member_ids = await self._run_sync(self.db.get_comm_dialog_members, dialog_id)
        await self._broadcast_to_user_ids(member_ids, {'type': 'comm_message_new', 'dialog_id': dialog_id, 'message': msg_obj})

    async def handle_send_comm_attachment(self, websocket, session, data):
        dialog_id = int(data.get('dialog_id') or 0)
        file_name = str(data.get('file_name') or '').strip()
        mime_type = str(data.get('mime_type') or '').strip()
        file_data_b64 = str(data.get('file_data_b64') or '')
        if dialog_id <= 0 or not file_name or not file_data_b64:
            return
        if not await self._run_sync(self.db.is_comm_dialog_member, dialog_id, session.user_id):
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'No access to this dialog'})
            return
        try:
            file_data = base64.b64decode(file_data_b64.encode('ascii'), validate=False)
        except Exception:
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'Invalid attachment data'})
            return
        if len(file_data) <= 0:
            return
        if len(file_data) > 8 * 1024 * 1024:
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'File too large (max 8MB)'})
            return
        msg_obj = await self._run_sync(self.db.create_comm_attachment_message, dialog_id, session.user_id, file_name, mime_type, file_data)
        if not msg_obj:
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'Attachment save failed'})
            return
        member_ids = await self._run_sync(self.db.get_comm_dialog_members, dialog_id)
        await self._broadcast_to_user_ids(member_ids, {'type': 'comm_message_new', 'dialog_id': dialog_id, 'message': msg_obj})

    async def handle_get_comm_attachment(self, websocket, session, data):
        message_id = int(data.get('message_id') or 0)
        if message_id <= 0:
            return
        att = await self._run_sync(self.db.get_comm_attachment, message_id)
        if not att:
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'Attachment not found'})
            return
        dialog_id = int(att.get('dialog_id') or 0)
        if dialog_id <= 0 or not await self._run_sync(self.db.is_comm_dialog_member, dialog_id, session.user_id):
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'No access to this attachment'})
            return
        payload_b64 = base64.b64encode(bytes(att.get('file_data') or b'')).decode('ascii')
        await self.send_json(websocket, {
            'type': 'comm_attachment_data',
            'message_id': message_id,
            'file_name': str(att.get('file_name') or 'file.bin'),
            'mime_type': str(att.get('mime_type') or ''),
            'file_size': int(att.get('file_size') or 0),
            'file_data_b64': payload_b64
        })

    async def handle_open_private_dialog(self, websocket, session, data):
        other_user_id = int(data.get('other_user_id') or 0)
        if other_user_id <= 0 or other_user_id == int(session.user_id):
            return
        dialog_id = await self._run_sync(self.db.get_or_create_private_dialog, int(session.user_id), other_user_id)
        if dialog_id <= 0:
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'Cannot open private dialog'})
            return
        member_ids = await self._run_sync(self.db.get_comm_dialog_members, dialog_id)
        await self._broadcast_to_user_ids(member_ids, {'type': 'comm_dialog_updated', 'dialog_id': dialog_id})
        await self.send_json(websocket, {'type': 'comm_private_dialog_opened', 'dialog_id': dialog_id})

    async def handle_leave_or_delete_comm_dialog(self, websocket, session, data):
        dialog_id = int(data.get('dialog_id') or 0)
        action = str(data.get('action') or '').strip().lower()
        if dialog_id <= 0 or action not in ('leave', 'delete'):
            return
        if not await self._run_sync(self.db.is_comm_dialog_member, dialog_id, session.user_id):
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'No access to this dialog'})
            return
        dlg = await self._run_sync(self.db.get_comm_dialog_by_id, dialog_id)
        if not dlg:
            return
        old_member_ids = await self._run_sync(self.db.get_comm_dialog_members, dialog_id)
        if action == 'delete':
            if int(dlg.get('created_by') or 0) != int(session.user_id) and str(session.role) != 'admin':
                await self.send_json(websocket, {'type': 'comm_error', 'message': 'Only owner can delete group'})
                return
            await self._run_sync(self.db.delete_comm_dialog, dialog_id)
            await self._broadcast_to_user_ids(old_member_ids, {
                'type': 'comm_dialog_removed',
                'dialog_id': dialog_id,
                'removed_for_all': 1
            })
            return
        # action == leave
        await self._run_sync(self.db.leave_comm_dialog, dialog_id, session.user_id)
        members_after = await self._run_sync(self.db.get_comm_dialog_members, dialog_id)
        await self._broadcast_to_user_ids(old_member_ids, {
            'type': 'comm_dialog_removed',
            'dialog_id': dialog_id,
            'removed_user_id': int(session.user_id),
            'removed_for_all': 0
        })
        if members_after:
            await self._broadcast_to_user_ids(members_after, {'type': 'comm_dialog_updated', 'dialog_id': dialog_id})

    async def handle_create_comm_task(self, websocket, session, data):
        payload = data.get('task') or {}
        title = str(payload.get('title') or '').strip()
        assignee_ids = payload.get('assignee_ids') or []
        if not assignee_ids and str(payload.get('assigned_to', '')).strip().isdigit():
            assignee_ids = [int(payload.get('assigned_to'))]
        watcher_ids = payload.get('watcher_ids') or []
        if not title or not assignee_ids:
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'Fill title and assignees'})
            return
        task = await self._run_sync(
            self.db.create_comm_task,
            title,
            str(payload.get('description') or '').strip(),
            assignee_ids,
            session.user_id,
            str(payload.get('deadline_date') or '').strip(),
            watcher_ids
        )
        if not task:
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'Task not created'})
            return
        participant_ids = await self._run_sync(self.db.get_comm_task_participants, int(task.get('task_id')))
        await self._broadcast_to_user_ids(participant_ids, {
            'type': 'comm_task_created',
            'task': task,
            'actor_user_id': int(session.user_id)
        })

    async def handle_update_comm_task_status(self, websocket, session, data):
        task_id = int(data.get('task_id') or 0)
        status = str(data.get('status') or 'new')
        if task_id <= 0:
            return
        if not await self._run_sync(self.db.can_user_update_comm_task, task_id, session.user_id):
            await self.send_json(websocket, {'type': 'comm_error', 'message': 'No access to update this task'})
            return
        task = await self._run_sync(self.db.update_comm_task_status, task_id, status)
        if not task:
            return
        participant_ids = await self._run_sync(self.db.get_comm_task_participants, task_id)
        await self._broadcast_to_user_ids(participant_ids, {
            'type': 'comm_task_updated',
            'task': task,
            'actor_user_id': int(session.user_id)
        })

    async def handle_message(self, websocket, message: str):
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ Ð¾Ñ‚ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')

            session = self.sessions.get_session(websocket)
            if not session:
                return

            # ÐŸÐ¾Ð´Ñ€Ð¾Ð±Ð½Ð¾Ðµ Ð»Ð¾Ð³Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ð´Ð»Ñ Ð¾Ñ‚Ð»Ð°Ð´ÐºÐ¸ Ð¿Ñ€Ð¾Ð±Ð»ÐµÐ¼ Ñ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒÑŽ
            if msg_type in ['labels_printed', 'boxes_info', 'order_printed']:
                logger.info(f"[MSG_DEBUG] ========================================")
                logger.info(f"[MSG_DEBUG] Ð¢Ð¸Ð¿ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ: {msg_type}")
                logger.info(f"[MSG_DEBUG] ÐžÑ‚ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ: {session.username}")
                logger.info(f"[MSG_DEBUG] Ð Ð¾Ð»ÑŒ: {session.role}")
                logger.info(f"[MSG_DEBUG] Ð”Ð°Ð½Ð½Ñ‹Ðµ: {data}")
                logger.info(f"[MSG_DEBUG] ========================================")

            logger.debug(f"ÐŸÐ¾Ð»ÑƒÑ‡ÐµÐ½Ð¾ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð¾Ñ‚ {session.username}: {msg_type}")
            await self._audit_user_action(session, websocket, msg_type, data)

            # ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ñ€Ð°Ð·Ð½Ñ‹Ñ… Ñ‚Ð¸Ð¿Ð¾Ð² ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ð¹
            if msg_type == 'get_comm_bootstrap':
                await self.handle_get_comm_bootstrap(websocket, session)
            elif msg_type == 'create_comm_dialog':
                await self.handle_create_comm_dialog(websocket, session, data)
            elif msg_type == 'add_comm_dialog_participants':
                await self.handle_add_comm_dialog_participants(websocket, session, data)
            elif msg_type == 'get_comm_messages':
                await self.handle_get_comm_messages(websocket, session, data)
            elif msg_type == 'get_comm_dialog_members':
                await self.handle_get_comm_dialog_members(websocket, session, data)
            elif msg_type == 'send_comm_message':
                await self.handle_send_comm_message(websocket, session, data)
            elif msg_type == 'send_comm_attachment':
                await self.handle_send_comm_attachment(websocket, session, data)
            elif msg_type == 'get_comm_attachment':
                await self.handle_get_comm_attachment(websocket, session, data)
            elif msg_type == 'open_private_dialog':
                await self.handle_open_private_dialog(websocket, session, data)
            elif msg_type == 'leave_or_delete_comm_dialog':
                await self.handle_leave_or_delete_comm_dialog(websocket, session, data)
            elif msg_type == 'create_comm_task':
                await self.handle_create_comm_task(websocket, session, data)
            elif msg_type == 'update_comm_task_status':
                await self.handle_update_comm_task_status(websocket, session, data)
            elif msg_type == 'create_user' and session.role == 'admin':
                await self.handle_create_user(websocket, data)

            elif msg_type == 'update_user' and session.role == 'admin':
                await self.handle_update_user(websocket, data)

            elif msg_type == 'delete_user' and session.role == 'admin':
                await self.handle_delete_user(websocket, data)

            elif msg_type == 'get_categories':
                await self.handle_get_categories(websocket, data)

            elif msg_type == 'add_category' and session.role == 'admin':
                await self.handle_add_category(websocket, data)

            elif msg_type == 'update_category' and session.role == 'admin':
                await self.handle_update_category(websocket, data)

            elif msg_type == 'delete_category' and session.role == 'admin':
                await self.handle_delete_category(websocket, data)

            elif msg_type == 'delete_order' and session.role == 'admin':
                await self.handle_delete_order(websocket, data)

            elif msg_type == 'create_manual_order' and session.role == 'admin':
                await self.handle_create_admin_order(websocket, data)

            elif msg_type == 'import_order_pdf' and session.role == 'admin':
                await self.handle_create_admin_order(websocket, data)

            elif msg_type == 'force_print' and session.role == 'admin':
                await self.handle_force_print(websocket, data)

            elif msg_type == 'delete_client' and session.role == 'admin':
                await self.handle_delete_client(websocket, data)
            
            elif msg_type == 'save_client_full' and session.role == 'admin':
                await self.handle_save_client_full(websocket, data)

            elif msg_type == 'restart_order' and session.role == 'admin':
                await self.handle_restart_order(websocket, data)

            elif msg_type == 'get_next_delivery_date' and session.role == 'admin':
                await self.handle_get_next_delivery_date(websocket, data)

            elif msg_type == 'move_order_next_route' and session.role == 'admin':
                await self.handle_move_order_next_logistics(websocket, data)

            elif msg_type == 'get_overdue_orders_preview' and session.role == 'admin':
                await self.handle_get_overdue_orders_preview(websocket, data)

            elif msg_type == 'bulk_reschedule_orders' and session.role == 'admin':
                await self.handle_bulk_reschedule_orders(websocket, data)

            elif msg_type == 'get_production_breakdown':
                await self.handle_get_production_breakdown(websocket, data)    

            elif msg_type == 'order_printed':
                # Ð’ÐÐ–ÐÐž: Ð’Ð¡Ð• Ñ€Ð¾Ð»Ð¸ Ð¼Ð¾Ð³ÑƒÑ‚ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÑÑ‚ÑŒ ÑÑ‚Ð°Ñ‚ÑƒÑ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ (operator, warehouse, admin)!
                await self.handle_order_printed(websocket, data)

            elif msg_type == 'labels_printed':
                # Ð’ÐÐ–ÐÐž: Ð’Ð¡Ð• Ñ€Ð¾Ð»Ð¸ Ð¼Ð¾Ð³ÑƒÑ‚ Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ñ‚ÑŒ Ð»ÐµÐ¹Ð±Ð»Ñ‹ (operator, warehouse, admin)!
                logger.info(f"[SERVER] âœ… ÐŸÐ¾Ð»ÑƒÑ‡ÐµÐ½Ð¾ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ labels_printed Ð¾Ñ‚ {session.username} (role={session.role})")
                logger.info(f"[SERVER] Ð”Ð°Ð½Ð½Ñ‹Ðµ: order_id={data.get('order_id')}, language={data.get('label_language')}")
                await self.handle_labels_printed(websocket, data)

            elif msg_type == 'boxes_info':
                # Ð’ÐÐ–ÐÐž: Ð’Ð¡Ð• Ñ€Ð¾Ð»Ð¸ Ð¼Ð¾Ð³ÑƒÑ‚ Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ñ‚ÑŒ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ¸ (operator, warehouse, admin)!
                logger.info(f"[SERVER] âœ… ÐŸÐ¾Ð»ÑƒÑ‡ÐµÐ½Ð¾ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ boxes_info Ð¾Ñ‚ {session.username} (role={session.role})")
                logger.info(f"[SERVER] Ð”Ð°Ð½Ð½Ñ‹Ðµ: order_id={data.get('order_id')}, count={data.get('boxes_count')}")
                await self.handle_boxes_info(websocket, data)

            elif msg_type == 'get_customer_shipping_doc':
                await self.handle_get_customer_shipping_doc(websocket, data)

            elif msg_type == 'download_invoice_file' and session.role == 'admin':
                await self.handle_download_invoice_file(websocket, data)

            elif msg_type == 'add_print_history':
                # Ð’ÐÐ–ÐÐž: Ð’Ð¡Ð• Ñ€Ð¾Ð»Ð¸ Ð¼Ð¾Ð³ÑƒÑ‚ Ð´Ð¾Ð±Ð°Ð²Ð»ÑÑ‚ÑŒ Ð¸ÑÑ‚Ð¾Ñ€Ð¸ÑŽ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ (operator, warehouse, admin)!
                await self.handle_add_print_history(websocket, data)

            elif msg_type == 'get_conditional_articles':
                await self.handle_get_conditional_articles(websocket)

            elif msg_type == 'search_warehouse_clients':
                await self.handle_search_warehouse_clients(websocket, data)

            elif msg_type == 'get_warehouse_print_settings':
                await self.handle_get_warehouse_print_settings(websocket)

            elif msg_type == 'save_warehouse_print_settings':
                await self.handle_save_warehouse_print_settings(websocket, data)

            elif msg_type == 'add_conditional_article' and session.role == 'admin':
                await self.handle_add_conditional_article(websocket, data)

            elif msg_type == 'remove_conditional_article' and session.role == 'admin':
                await self.handle_remove_conditional_article(websocket, data)

            elif msg_type == 'save_picking_progress':
                # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ Ð¿Ñ€Ð°Ð²Ð° Ð½Ð° ÑÐºÐ»Ð°Ð´
                user_perms = [p.strip() for p in (session.permissions or '').split(',') if p.strip()]
                has_warehouse = session.role == 'warehouse' or 'warehouse' in user_perms
                if has_warehouse:
                    await self.handle_save_picking_progress(websocket, data)

            elif msg_type == 'assign_order':
                # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ Ð¿Ñ€Ð°Ð²Ð° Ð½Ð° ÑÐºÐ»Ð°Ð´
                user_perms = [p.strip() for p in (session.permissions or '').split(',') if p.strip()]
                has_warehouse = session.role == 'warehouse' or 'warehouse' in user_perms
                if has_warehouse:
                    await self.handle_assign_order(websocket, data)

            elif msg_type == 'get_picking_statistics' and session.role in ['operator', 'admin']:
                await self.handle_get_picking_statistics(websocket, data)

            # ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚Ñ‡Ð¸ÐºÐ¸ Ð¸Ð½Ð²ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð·Ð°Ñ†Ð¸Ð¸ (ÑÐºÐ»Ð°Ð´)
            elif msg_type == 'get_inventory_articles':
                user_perms = [p.strip() for p in (session.permissions or '').split(',') if p.strip()]
                has_warehouse = session.role == 'warehouse' or 'warehouse' in user_perms
                if has_warehouse or session.role == 'admin':
                    await self.handle_get_inventory_articles(websocket)

            elif msg_type == 'save_daily_stock_report':
                user_perms = [p.strip() for p in (session.permissions or '').split(',') if p.strip()]
                has_warehouse = session.role == 'warehouse' or 'warehouse' in user_perms
                if has_warehouse or session.role == 'admin':
                    await self.handle_save_daily_stock_report(websocket, data)

            elif msg_type == 'get_daily_stock_report':
                user_perms = [p.strip() for p in (session.permissions or '').split(',') if p.strip()]
                has_warehouse = session.role == 'warehouse' or 'warehouse' in user_perms
                if has_warehouse or session.role == 'admin':
                    await self.handle_get_daily_stock_report(websocket, data)

            elif msg_type == 'get_recipes' and session.role == 'admin':
                await self.handle_get_recipes(websocket)

            elif msg_type == 'toggle_recipe_active' and session.role == 'admin':
                await self.handle_toggle_recipe_active(websocket, data)

            elif msg_type == 'save_dough_type' and session.role == 'admin':
                await self.handle_save_dough_type(websocket, data)

            elif msg_type == 'delete_dough_type' and session.role == 'admin':
                await self.handle_delete_dough_type(websocket, data)

            elif msg_type == 'save_recipe' and session.role == 'admin':
                await self.handle_save_recipe(websocket, data)

            elif msg_type == 'save_recipe_extended' and session.role == 'admin':
                await self.handle_save_recipe_extended(websocket, data)

            elif msg_type == 'delete_recipe' and session.role == 'admin':
                await self.handle_delete_recipe(websocket, data)

            elif msg_type == 'import_recipes_from_orders' and session.role == 'admin':
                await self.handle_import_recipes_from_orders(websocket)

            elif msg_type == 'get_production_rules' and session.role == 'admin':
                await self.handle_get_production_rules(websocket)

            elif msg_type == 'get_production_rule' and session.role == 'admin':
                await self.handle_get_production_rule(websocket, data)

            elif msg_type == 'save_production_rule' and session.role == 'admin':
                await self.handle_save_production_rule(websocket, data)

            elif msg_type == 'delete_production_rule' and session.role == 'admin':
                await self.handle_delete_production_rule(websocket, data)

            elif msg_type == 'calculate_production_plan' and session.role == 'admin':
                await self.handle_calculate_production_plan(websocket, data)

            elif msg_type == 'calculate_weekly_production_plan' and session.role == 'admin':
                await self.handle_calculate_weekly_production_plan(websocket, data)

            elif msg_type == 'get_daily_shipping_summary':
                # Ð¡Ð²Ð¾Ð´Ð½Ð°Ñ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ð° Ð¾Ñ‚Ð³Ñ€ÑƒÐ·Ð¾Ðº Ð½Ð° Ð´ÐµÐ½ÑŒ (Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð½Ð° Ð²ÑÐµÐ¼ Ñ Ð¿Ñ€Ð°Ð²Ð¾Ð¼ production)
                user_perms = [p.strip() for p in (session.permissions or '').split(',') if p.strip()]
                if session.role == 'admin' or 'production' in user_perms or 'admin' in user_perms:
                    await self.handle_get_daily_shipping_summary(websocket, data)

            elif msg_type == 'get_shipping_summary_settings':
                user_perms = [p.strip() for p in (session.permissions or '').split(',') if p.strip()]
                if session.role == 'admin' or 'production' in user_perms or 'admin' in user_perms:
                    await self.handle_get_shipping_summary_settings(websocket, session)

            elif msg_type == 'save_shipping_summary_settings':
                user_perms = [p.strip() for p in (session.permissions or '').split(',') if p.strip()]
                if session.role == 'admin' or 'production' in user_perms or 'admin' in user_perms:
                    await self.handle_save_shipping_summary_settings(websocket, data, session)

            elif msg_type == 'get_admin_orders_settings' and session.role == 'admin':
                await self.handle_get_admin_orders_settings(websocket, session)

            elif msg_type == 'save_admin_orders_settings' and session.role == 'admin':
                await self.handle_save_admin_orders_settings(websocket, data, session)

            elif msg_type == 'update_production_fact' and session.role == 'admin':
                await self.handle_update_production_fact(websocket, data)

            elif msg_type == 'adjust_stock' and session.role == 'admin':
                await self.handle_adjust_stock(websocket, data)

            elif msg_type == 'save_plan_settings' and session.role == 'admin':
                await self.handle_save_plan_settings(websocket, data, session)

            elif msg_type == 'get_plan_settings':
                await self.handle_get_plan_settings(websocket, session)

            elif msg_type == 'get_backup_settings' and session.role == 'admin':
                await self.handle_get_backup_settings(websocket, session)

            elif msg_type == 'get_backup_history' and session.role == 'admin':
                await self.handle_get_backup_history(websocket, session)

            elif msg_type == 'save_backup_settings' and session.role == 'admin':
                await self.handle_save_backup_settings(websocket, data, session)

            elif msg_type == 'run_backup_now' and session.role == 'admin':
                await self.handle_run_backup_now(websocket, data, session)

            elif msg_type == 'get_server_status' and session.role == 'admin':
                await self.handle_get_server_status(websocket, session)

            elif msg_type == 'get_user_activity_logs' and session.role == 'admin':
                await self.handle_get_user_activity_logs(websocket, data, session)

            elif msg_type == 'get_client_order_history' and session.role == 'admin':
                await self.handle_get_client_order_history(websocket, data, session)

            elif msg_type == 'ui_interaction':
                # Событие уже записано в аудит через _audit_user_action; отдельной обработки не требуется.
                pass

            elif msg_type == 'disconnect_session' and session.role == 'admin':
                await self.handle_disconnect_session(websocket, data, session)

            elif msg_type == 'restart_server' and session.role == 'admin':
                await self.handle_restart_server(websocket, data, session)

            elif msg_type == 'get_recipe_bom' and session.role == 'admin':
                await self.handle_get_recipe_bom(websocket, data)

            elif msg_type == 'get_dough_composition' and session.role == 'admin':
                await self.handle_get_dough_composition(websocket, data)

            elif msg_type == 'save_daily_stock' and session.role == 'admin':
                await self.handle_save_daily_stock(websocket, data)

            elif msg_type == 'get_daily_stock' and session.role == 'admin':
                await self.handle_get_daily_stock(websocket, data)

            elif msg_type == 'update_order_date':
                await self.handle_update_order_date(websocket, data)
            
            elif msg_type == 'recalc_order_logistics':
                await self.handle_recalc_order_logistics(websocket, data)

            elif msg_type == 'create_route':
                await self.handle_create_route(websocket, data)
            elif msg_type == 'update_route_name':
                await self.handle_update_route_name(websocket, data)
            elif msg_type == 'delete_route':
                await self.handle_delete_route(websocket, data)    

            elif msg_type == 'save_substitution' and session.role == 'admin':
                def _save_sub():
                    with self.db.safe_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("INSERT OR REPLACE INTO product_substitutions VALUES (?, ?)",
                                     (data['old'], data['new']))
                        conn.commit()
                await self._run_sync(_save_sub)

            elif msg_type == 'get_history_orders' and session.role == 'admin':
                target_date = data.get('date')
                logger.info(f"ÐÐ´Ð¼Ð¸Ð½ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¸Ð» Ð¸ÑÑ‚Ð¾Ñ€Ð¸ÑŽ Ð·Ð° {target_date}")
                orders = await self._run_sync(self.db.get_orders_by_date, target_date)
                await websocket.send(json.dumps({
                    'type': 'history_data',
                    'date': target_date,
                    'orders': orders
                }))
            # === ÐÐžÐ’ÐžÐ• Ð£Ð¡Ð›ÐžÐ’Ð˜Ð• Ð”Ð›Ð¯ Ð‘Ð›ÐžÐšÐ˜Ð ÐžÐ’ÐšÐ˜ Ð—ÐÐšÐÐ—Ð ===
            elif msg_type == 'start_viewing_order' and session.role == 'warehouse':
                await self.handle_start_viewing_order(websocket, data)
            # ===========================================

            elif msg_type == 'refresh_orders':
                # Ð›ÑŽÐ±Ð°Ñ Ñ€Ð¾Ð»ÑŒ Ð¼Ð¾Ð¶ÐµÑ‚ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¸Ñ‚ÑŒ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²
                logger.info(f"ðŸ“¡ Refresh orders requested by {session.username}")
                # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½Ñ‹Ð¹ User Ð¾Ð±ÑŠÐµÐºÑ‚ Ð¸Ð· ÑÐµÑÑÐ¸Ð¸
                user = User(
                    user_id=session.user_id,
                    username=session.username,
                    role=session.role,
                    warehouse_id=session.warehouse_id
                )
                await self.send_initial_data(websocket, user)
                logger.info(f"âœ“ Refresh orders sent to {session.username}")

            elif msg_type == 'refresh_with_api_scan':
                # ÐŸÑ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ð¹ API scan + Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ Ð·Ð°ÐºÐ°Ð·Ð¾Ð² (Ð²ÑÐµ Ñ€Ð¾Ð»Ð¸)
                # Ð—Ð°Ñ‰Ð¸Ñ‚Ð° Ð¾Ñ‚ Ð¿Ð¾Ð²Ñ‚Ð¾Ñ€Ð½Ñ‹Ñ… Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð²: ÐµÑÐ»Ð¸ scan ÑƒÐ¶Ðµ Ð¸Ð´Ñ‘Ñ‚, Ð¿Ñ€Ð¾Ð¿ÑƒÑÐºÐ°ÐµÐ¼ scan Ð¸ Ð¿Ñ€Ð¾ÑÑ‚Ð¾ ÑˆÐ»Ñ‘Ð¼ Ð´Ð°Ð½Ð½Ñ‹Ðµ
                logger.info(f"ðŸ“¡ Refresh with API scan requested by {session.username}")
                if self._api_scan_lock and not self._api_scan_lock.locked():
                    async with self._api_scan_lock:
                        try:
                            self.api_monitor.last_fetch_time = None
                            loop = asyncio.get_event_loop()
                            executor = getattr(self, '_monitor_executor', None)
                            await asyncio.wait_for(
                                loop.run_in_executor(executor, self.api_monitor.scan),
                                timeout=60
                            )
                        except asyncio.TimeoutError:
                            logger.warning("API scan timed out during refresh")
                        except Exception as e:
                            logger.warning(f"API scan error during refresh: {e}")
                else:
                    logger.info(f"â­ API scan already running, skipping for {session.username}")
                user = User(
                    user_id=session.user_id,
                    username=session.username,
                    role=session.role,
                    warehouse_id=session.warehouse_id
                )
                await self.send_initial_data(websocket, user)
                logger.info(f"âœ“ Refresh with API scan sent to {session.username}")

            elif msg_type == 'get_all_logistics' and session.role == 'admin':
                await self.handle_get_all_logistics(websocket)

            elif msg_type == 'save_logistics_rule' and session.role == 'admin':
                await self.handle_save_logistics_rule(websocket, data)

            elif msg_type == 'update_logistics_route' and session.role == 'admin':
                await self.handle_update_logistics_route(websocket, data)

            elif msg_type == 'update_client_logistics' and session.role == 'admin':
                await self.handle_update_client_logistics(websocket, data)

            # --- MARK AS REVIEWED (ÑÐ½ÑÑ‚Ð¸Ðµ Ð¼ÐµÑ‚ÐºÐ¸ NEW) ---
            elif msg_type == 'mark_client_reviewed' and session.role == 'admin':
                client_id = data.get('client_id')
                if client_id:
                    await self._run_sync(self.db.mark_client_reviewed, client_id)
                    await self.broadcast_logistics_update()

            elif msg_type == 'mark_all_clients_reviewed' and session.role == 'admin':
                count = await self._run_sync(self.db.mark_all_clients_reviewed)
                logger.info(f"Marked {count} clients as reviewed")
                await self.broadcast_logistics_update()

            elif msg_type == 'mark_recipe_reviewed' and session.role == 'admin':
                article_nr = data.get('article_nr')
                if article_nr:
                    await self._run_sync(self.db.mark_recipe_reviewed, article_nr)
                    await self.handle_get_recipes(websocket)

            elif msg_type == 'mark_all_recipes_reviewed' and session.role == 'admin':
                count = await self._run_sync(self.db.mark_all_recipes_reviewed)
                logger.info(f"Marked {count} recipes as reviewed")
                await self.handle_get_recipes(websocket)

            # ============================================
            # MONOLITH API: ÐœÐ°Ð¿Ð¿Ð¸Ð½Ð³ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
            # ============================================

            elif msg_type == 'get_article_mappings' and session.role == 'admin':
                await self.handle_get_article_mappings(websocket)

            elif msg_type == 'save_article_mapping' and session.role == 'admin':
                await self.handle_save_article_mapping(websocket, data)

            elif msg_type == 'delete_article_mapping' and session.role == 'admin':
                await self.handle_delete_article_mapping(websocket, data)

            elif msg_type == 'save_client_monolith_id' and session.role == 'admin':
                await self.handle_save_client_monolith_id(websocket, data)

            elif msg_type == 'mark_api_order_seen':
                await self.handle_mark_api_order_seen(websocket, data)

            elif msg_type == 'auto_fill_prices' and session.role == 'admin':
                await self.handle_auto_fill_prices(websocket)

            elif msg_type == 'force_api_scan' and session.role == 'admin':
                await self.handle_force_api_scan(websocket)

            elif msg_type == 'get_resources' and session.role == 'admin':
                # Get all resources with capacities
                resources = self.resource_manager.get_all_resources_capacity()
                await websocket.send(json.dumps({
                    'type': 'resources_data',
                    'resources': resources
                }))

            elif msg_type == 'update_resource' and session.role == 'admin':
                # Update resource parameters
                resource_id = data.get('resource_id')
                updates = data.get('updates', {})

                success = self.resource_manager.update_resource(resource_id, **updates)

                if success:
                    logger.info(f"âœ“ Resource {resource_id} updated: {updates}")

                    # Broadcast to all admins
                    updated_resources = self.resource_manager.get_all_resources_capacity()
                    await self.sessions.broadcast_to_admins({
                        'type': 'resources_update',
                        'resources': updated_resources
                    })

                    await websocket.send(json.dumps({
                        'type': 'success',
                        'message': 'Resource updated successfully'
                    }))
                else:
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'message': 'Failed to update resource'
                    }))

            elif msg_type == 'add_resource' and session.role == 'admin':
                # Add new resource
                resource_data = data.get('resource_data', {})

                success = self.resource_manager.add_resource(resource_data)

                if success:
                    logger.info(f"âœ“ Resource added: {resource_data.get('resource_name')}")

                    # Broadcast to all admins
                    updated_resources = self.resource_manager.get_all_resources_capacity()
                    await self.sessions.broadcast_to_admins({
                        'type': 'resources_update',
                        'resources': updated_resources
                    })

                    await websocket.send(json.dumps({
                        'type': 'success',
                        'message': 'Resource added successfully'
                    }))
                else:
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'message': 'Failed to add resource'
                    }))

            elif msg_type == 'delete_resource' and session.role == 'admin':
                # Delete resource
                resource_id = data.get('resource_id')

                success = self.resource_manager.delete_resource(resource_id)

                if success:
                    logger.info(f"âœ“ Resource {resource_id} deleted")

                    # Broadcast to all admins
                    updated_resources = self.resource_manager.get_all_resources_capacity()
                    await self.sessions.broadcast_to_admins({
                        'type': 'resources_update',
                        'resources': updated_resources
                    })

                    await websocket.send(json.dumps({
                        'type': 'success',
                        'message': 'Resource deleted successfully'
                    }))
                else:
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'message': 'Failed to delete resource'
                    }))

            elif msg_type == 'get_article_resource_consumption' and session.role == 'admin':
                # Get resource consumption for specific article
                article_nr = data.get('article_nr')

                conn = self.db.get_connection()
                cursor = conn.cursor()

                cursor.execute('''
                    SELECT resource_id, time_needed_min, comments
                    FROM product_resource_consumption
                    WHERE article_nr = ?
                ''', (article_nr,))

                consumption = []
                for row in cursor.fetchall():
                    consumption.append({
                        'resource_id': row[0],
                        'time_needed_min': row[1],
                        'comments': row[2] if row[2] else ''
                    })

                conn.close()

                await websocket.send(json.dumps({
                    'type': 'article_resource_consumption',
                    'article_nr': article_nr,
                    'consumption': consumption
                }))

            # =========================================================================
            # ZUTATEN V2: Ð£Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ Ð¸Ð½Ð³Ñ€ÐµÐ´Ð¸ÐµÐ½Ñ‚Ð°Ð¼Ð¸ (LMIV EU 1169/2011)
            # =========================================================================
            elif msg_type in self.zutaten_handlers:
                # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ Ð¿Ñ€Ð°Ð²Ð° Ð´Ð¾ÑÑ‚ÑƒÐ¿Ð° (Ñ‚Ð¾Ð»ÑŒÐºÐ¾ admin Ð´Ð»Ñ Ð·Ð°Ð¿Ð¸ÑÐ¸, Ñ‡Ñ‚ÐµÐ½Ð¸Ðµ/Ð³ÐµÐ½ÐµÑ€Ð°Ñ†Ð¸Ñ Ð´Ð»Ñ Ð²ÑÐµÑ…)
                admin_only_zutaten = {
                    'save_ingredient', 'delete_ingredient', 'save_recipe_ingredients',
                    'save_allergen', 'delete_allergen', 'save_recipe_label_data', 'save_label_setting',
                    'sync_label_from_tree',
                    # V2: Ð´ÐµÑ€ÐµÐ²Ð¾ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² Ð¸ Ð¿Ð¾Ð´Ñ‚Ð²ÐµÑ€Ð¶Ð´ÐµÐ½Ð¸Ðµ ÑÐ¾ÑÑ‚Ð°Ð²Ð°
                    'save_recipe_tree', 'add_tree_node', 'update_tree_node', 'delete_tree_node',
                    'confirm_composition', 'invalidate_composition_cache',
                }
                if msg_type in admin_only_zutaten:
                    if session.role not in ['admin', 'operator']:
                        await websocket.send(json.dumps({
                            'type': 'error',
                            'message': 'Admin or operator access required'
                        }))
                        return
                await self.zutaten_handlers[msg_type](websocket, data)

            elif msg_type == 'ping':
                await websocket.send(json.dumps({'type': 'pong'}))

        except Exception as e:
            logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ: {e}")
            try:
                self.db.log_error('server', 'message_error', str(e))
            except Exception as log_err:
                logger.error(f"[ERROR_LOG] failed to write log_error: {log_err}")

    # ============================================
    # ÐžÐ‘Ð ÐÐ‘ÐžÐ¢Ð§Ð˜ÐšÐ˜ ÐšÐžÐœÐÐÐ”
    # ============================================
    async def handle_create_user(self, websocket, data):
        """Ð¡Ð¾Ð·Ð´Ð°Ñ‚ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ (Ð¡ ÐŸÐ ÐÐ’ÐÐœÐ˜)"""
        username = data.get('username')
        password = data.get('password')
        role = data.get('role')
        warehouse_id = data.get('warehouse_id')
        permissions = data.get('permissions') # <--- ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð¿Ñ€Ð°Ð²Ð°
        first_name = data.get('first_name')
        last_name = data.get('last_name')

        # ÐŸÐµÑ€ÐµÐ´Ð°ÐµÐ¼ permissions Ð² Ð±Ð°Ð·Ñƒ
        success = self.db.create_user(username, password, role, warehouse_id, permissions, first_name, last_name)

        if success:
            await websocket.send(json.dumps({'type': 'user_created', 'username': username}))
            # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ ÑÐ¿Ð¸ÑÐ¾Ðº Ñƒ Ð°Ð´Ð¼Ð¸Ð½Ð¾Ð²
            users = self.db.get_all_users()
            await self.sessions.broadcast_to_admins({'type': 'users_update', 'users': users})
        else:
            await websocket.send(json.dumps({'type': 'error', 'message': 'User exists'}))

    async def handle_start_viewing_order(self, websocket, data):
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° ÑÐ¸Ð³Ð½Ð°Ð»Ð°: ÐŸÐ¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒ Ð½Ð°Ñ‡Ð°Ð» Ð¿Ñ€Ð¾ÑÐ¼Ð¾Ñ‚Ñ€ Ð·Ð°ÐºÐ°Ð·Ð° (Ð‘Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²ÐºÐ°)"""
        order_id = data.get('order_id')
    
        # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ ÑÐµÑÑÐ¸ÑŽ Ñ‚Ð¾Ð³Ð¾, ÐºÑ‚Ð¾ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð¸Ð» Ð·Ð°Ð¿Ñ€Ð¾Ñ
        session = self.sessions.get_session(websocket)
        if not session: return

        username = session.username
    
        # ÐœÑ‹ Ð½Ðµ ÑÐ¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ ÑÑ‚Ð¾ Ð² Ð‘Ð” (ÑÑ‚Ð¾ Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½Ð¾Ðµ ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ "Ð¿Ñ€ÑÐ¼Ð¾ ÑÐµÐ¹Ñ‡Ð°Ñ"),
        # Ð½Ð¾ Ð¼Ñ‹ Ð¼Ð¾Ð¶ÐµÐ¼ Ð¾Ð±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ Ð² Ð¿Ð°Ð¼ÑÑ‚Ð¸, ÐµÑÐ»Ð¸ Ð½ÑƒÐ¶Ð½Ð¾.
        # Ð“Ð»Ð°Ð²Ð½Ð¾Ðµ - ÑƒÐ²ÐµÐ´Ð¾Ð¼Ð¸Ñ‚ÑŒ Ð²ÑÐµÑ… Ð¾ÑÑ‚Ð°Ð»ÑŒÐ½Ñ‹Ñ….
    
        # Ð Ð°ÑÑÑ‹Ð»Ð°ÐµÐ¼ Ð²ÑÐµÐ¼ Warehouse ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼ (Ð¸ Ð¼Ð¾Ð¶Ð½Ð¾ Ð¾Ð¿ÐµÑ€Ð°Ñ‚Ð¾Ñ€Ð°Ð¼)
        # Ð¡Ð¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ: "order_id Ñ‚ÐµÐ¿ÐµÑ€ÑŒ Ð·Ð°Ð½ÑÑ‚ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¼ username"
        await self.sessions.broadcast_to_all({
            'type': 'order_viewing_update',
            'order_id': order_id,
            'username': username,
            'timestamp': datetime.now().isoformat()
        })
    
        logger.info(f"Lock: User {username} is viewing order {order_id}")        

    async def handle_update_user(self, websocket, data):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ (Ð¡ ÐŸÐ ÐÐ’ÐÐœÐ˜)"""
        user_id = data.get('user_id')
        username = data.get('username')
        password = data.get('password')
        role = data.get('role')
        warehouse_id = data.get('warehouse_id')
        permissions = data.get('permissions') # <--- ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð¿Ñ€Ð°Ð²Ð°
        first_name = data.get('first_name')
        last_name = data.get('last_name')

        # ÐŸÐµÑ€ÐµÐ´Ð°ÐµÐ¼ permissions Ð² Ð±Ð°Ð·Ñƒ
        success = self.db.update_user(user_id, username, password, role, warehouse_id, permissions, first_name, last_name)

        if success:
            users = self.db.get_all_users()
            await self.sessions.broadcast_to_admins({'type': 'users_update', 'users': users})
        else:
            await websocket.send(json.dumps({'type': 'error', 'message': 'Update failed'}))

    async def handle_delete_user(self, websocket, data):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ"""
        user_id = data.get('user_id')

        success = self.db.delete_user(user_id)

        if success:
            # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ ÑÐ¿Ð¸ÑÐ¾Ðº Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¹ Ð´Ð»Ñ Ð²ÑÐµÑ… Ð°Ð´Ð¼Ð¸Ð½Ð¾Ð²
            users = self.db.get_all_users()
            await self.sessions.broadcast_to_admins({
                'type': 'users_update',
                'users': users
            })

            logger.info(f"Ð£Ð´Ð°Ð»Ñ‘Ð½ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒ ID: {user_id}")

    async def handle_get_categories(self, websocket, data):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº Ð²ÑÐµÑ… ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¹"""
        categories = self.db.get_all_categories()

        await websocket.send(json.dumps({
            'type': 'categories_data',
            'categories': categories
        }))

    async def handle_add_category(self, websocket, data):
        """Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð½Ð¾Ð²ÑƒÑŽ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸ÑŽ"""
        category_id = data.get('category_id')
        category_name = data.get('category_name')
        workshop_name = data.get('workshop_name', '')
        description = data.get('description', '')
        color = data.get('color', '#95a5a6')

        success = self.db.add_category(category_id, category_name, workshop_name, description, color)

        if success:
            # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ ÑÐ¿Ð¸ÑÐ¾Ðº ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¹ Ð´Ð»Ñ Ð²ÑÐµÑ… Ð°Ð´Ð¼Ð¸Ð½Ð¾Ð²
            categories = self.db.get_all_categories()
            await self.sessions.broadcast_to_admins({
                'type': 'categories_update',
                'categories': categories
            })

            logger.info(f"Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð° ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ: {category_id} - {category_name}")

    async def handle_update_category(self, websocket, data):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸ÑŽ"""
        category_id = data.get('category_id')
        category_name = data.get('category_name')
        workshop_name = data.get('workshop_name', '')
        description = data.get('description', '')
        color = data.get('color', '#95a5a6')
        active = data.get('active', 1)

        success = self.db.update_category(category_id, category_name, workshop_name,
                                         description, color, active)

        if success:
            # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ ÑÐ¿Ð¸ÑÐ¾Ðº ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¹ Ð´Ð»Ñ Ð²ÑÐµÑ… Ð°Ð´Ð¼Ð¸Ð½Ð¾Ð²
            categories = self.db.get_all_categories()
            await self.sessions.broadcast_to_admins({
                'type': 'categories_update',
                'categories': categories
            })

            logger.info(f"ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð° ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ: {category_id} - {category_name}")

    async def handle_delete_category(self, websocket, data):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸ÑŽ (ÐŸÐ¾ ID Ð¸Ð»Ð¸ Ð¿Ð¾ Ð˜Ð¼ÐµÐ½Ð¸)"""
        cat_id = data.get('category_id') # Ð¡ÑŽÐ´Ð° ÐºÐ»Ð¸ÐµÐ½Ñ‚ Ð¼Ð¾Ð¶ÐµÑ‚ Ð¿Ñ€Ð¸ÑÐ»Ð°Ñ‚ÑŒ Ð¸Ð¼Ñ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¸

        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Ð¡Ð½Ð°Ñ‡Ð°Ð»Ð° Ð¿Ñ€Ð¾Ð±ÑƒÐµÐ¼ ÑƒÐ´Ð°Ð»Ð¸Ñ‚ÑŒ Ð¿Ð¾ ID
            cursor.execute("DELETE FROM categories WHERE category_id = ?", (cat_id,))
        
            # Ð•ÑÐ»Ð¸ Ð½Ðµ ÑƒÐ´Ð°Ð»Ð¸Ð»Ð¾ÑÑŒ (0 ÑÑ‚Ñ€Ð¾Ðº), Ð¿Ñ€Ð¾Ð±ÑƒÐµÐ¼ ÑƒÐ´Ð°Ð»Ð¸Ñ‚ÑŒ Ð¿Ð¾ Ð˜ÐœÐ•ÐÐ˜
            if cursor.rowcount == 0:
                cursor.execute("DELETE FROM categories WHERE category_name = ?", (cat_id,))
        
            conn.commit()

            logger.info(f"Ð£Ð´Ð°Ð»ÐµÐ½Ð° ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ: {cat_id}")
        
            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð½Ñ‹Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº Ð²ÑÐµÐ¼, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ñƒ Ð²ÑÐµÑ… Ð¸ÑÑ‡ÐµÐ·Ð»Ð° ÑÑ‚Ð° ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ
            categories = self.db.get_all_categories()
            # ÐÐ°Ð¼ Ð½ÑƒÐ¶Ð½Ð¾ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð¸Ñ‚ÑŒ Ð¸Ð¼ÐµÐ½Ð½Ð¾ Ñ‚Ð¾Ñ‚ Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚, ÐºÐ¾Ñ‚Ð¾Ñ€Ñ‹Ð¹ Ð¶Ð´ÐµÑ‚ ÐºÐ»Ð¸ÐµÐ½Ñ‚ Ð² recipes_data
            # ÐÐ¾ Ð¿Ñ€Ð¾Ñ‰Ðµ Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð·Ð°ÑÑ‚Ð°Ð²Ð¸Ñ‚ÑŒ Ð°Ð´Ð¼Ð¸Ð½Ð¾Ð² Ð¾Ð±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ñ‹
        
            # Ð’ Ð´Ð°Ð½Ð½Ð¾Ð¼ ÑÐ»ÑƒÑ‡Ð°Ðµ ÐºÐ»Ð¸ÐµÐ½Ñ‚ ÑÐ°Ð¼ ÑƒÐ´Ð°Ð»Ð¸Ð» Ñƒ ÑÐµÐ±Ñ Ð¸Ð· ÑÐ¿Ð¸ÑÐºÐ°,
            # Ð³Ð»Ð°Ð²Ð½Ð¾Ðµ, Ñ‡Ñ‚Ð¾Ð±Ñ‹ ÑÐµÑ€Ð²ÐµÑ€ Ð½Ðµ Ð¿Ñ€Ð¸ÑÐ»Ð°Ð» ÑÑ‚Ð¾ ÑÐ½Ð¾Ð²Ð° Ð¿Ñ€Ð¸ Ð¿ÐµÑ€ÐµÐ·Ð°Ð³Ñ€ÑƒÐ·ÐºÐµ.
        
        except Exception as e:
            logger.error(f"Error deleting category: {e}")
        finally:
            conn.close()

    async def handle_create_admin_order(self, websocket, data):
        """Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¸Ðµ Ð·Ð°ÐºÐ°Ð·Ð° Ð°Ð´Ð¼Ð¸Ð½Ð¸ÑÑ‚Ñ€Ð°Ñ‚Ð¾Ñ€Ð¾Ð¼ (Ñ€ÑƒÑ‡Ð½Ð¾Ð¹ Ð²Ð²Ð¾Ð´ Ð¸Ð»Ð¸ Ð¸Ð¼Ð¿Ð¾Ñ€Ñ‚ PDF)."""
        source_type = 'manual'
        if str(data.get('type') or '').strip().lower() == 'import_order_pdf':
            source_type = 'pdf'
        import_file_name = str(data.get('file_name') or '').strip()

        payload = data.get('order') or {}
        source_prefix = str(payload.get('source_prefix') or 'AB').strip().upper()
        order_number = str(payload.get('order_number') or '').strip()
        if not order_number:
            await websocket.send(json.dumps({
                'type': 'admin_order_created',
                'success': False,
                'error': 'ÐÐµ ÑƒÐºÐ°Ð·Ð°Ð½ Ð½Ð¾Ð¼ÐµÑ€ Ð·Ð°ÐºÐ°Ð·Ð°'
            }))
            return

        if '-' in order_number and order_number.split('-', 1)[0].upper() in ('AB', 'MO', 'LS'):
            order_id = order_number
            auftrag_nr = order_number.split('-', 1)[1]
        else:
            order_id = f"{source_prefix}-{order_number}"
            auftrag_nr = order_number

        if self.db.order_exists(order_id):
            await websocket.send(json.dumps({
                'type': 'admin_order_created',
                'success': False,
                'error': f'Ð—Ð°ÐºÐ°Ð· {order_id} ÑƒÐ¶Ðµ ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÐµÑ‚'
            }))
            return

        kunden_nr = str(payload.get('kunden_nr') or '').strip()
        kunde = str(payload.get('kunde') or '').strip()
        address = str(payload.get('address') or '').strip()
        route_id_manual = str(payload.get('route_id') or '').strip()
        order_date = str(payload.get('order_date') or datetime.now().strftime('%Y-%m-%d')).strip()
        delivery_override = str(payload.get('delivery_date') or '').strip()

        # Ð˜Ñ‰ÐµÐ¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð° Ð² Ð±Ð°Ð·Ðµ Ð»Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÐ¸ Ð¿Ð¾ ID, ÐµÑÐ»Ð¸ ÐµÑÑ‚ÑŒ - Ð±ÐµÑ€Ñ‘Ð¼ ÐµÐ³Ð¾ Ð´Ð°Ð½Ð½Ñ‹Ðµ.
        client_found = False
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            row = None
            if kunden_nr:
                cursor.execute("""
                    SELECT client_id, client_name, address, plz, city, route_id
                    FROM client_routes
                    WHERE client_id = ?
                    LIMIT 1
                """, (kunden_nr,))
                row = cursor.fetchone()
            if not row and kunde:
                cursor.execute("""
                    SELECT client_id, client_name, address, plz, city, route_id
                    FROM client_routes
                    WHERE lower(client_name) = lower(?)
                    LIMIT 1
                """, (kunde,))
                row = cursor.fetchone()
            conn.close()
            if row:
                client_found = True
                kunden_nr = kunden_nr or str(row['client_id'] or '').strip()
                kunde = kunde or str(row['client_name'] or '').strip()
                if not address:
                    a = str(row['address'] or '').strip()
                    p = str(row['plz'] or '').strip()
                    c = str(row['city'] or '').strip()
                    address = ", ".join([x for x in (a, p, c) if x])
                if not route_id_manual:
                    route_id_manual = str(row['route_id'] or '').strip()
        except Exception as e:
            logger.warning(f"Client lookup failed for manual order {order_id}: {e}")

        # ÐÐ¾Ñ€Ð¼Ð°Ð»Ð¸Ð·ÑƒÐµÐ¼ Ð¿Ð¾Ð·Ð¸Ñ†Ð¸Ð¸
        artikel_raw = payload.get('artikel') or []
        artikel_list = []
        for idx, a in enumerate(artikel_raw, start=1):
            art_raw = str(a.get('artikel_nr') or a.get('nummer') or '').strip()
            art_raw = art_raw.replace(' ', '')
            if '.' in art_raw and art_raw.replace('.', '').isdigit():
                art_raw = art_raw.split('.', 1)[0]
            art_nr = art_raw.zfill(5) if art_raw.isdigit() else art_raw
            if not art_nr:
                continue
            try:
                qty = float(str(a.get('menge', 0)).replace(',', '.'))
            except Exception:
                qty = 0.0
            if qty <= 0:
                continue
            name = str(a.get('name') or a.get('beschreibung') or '').strip()
            artikel_list.append({
                'pos': idx,
                'artikel_nr': art_nr,
                'nummer': art_nr,
                'name': name,
                'beschreibung': name,
                'menge': qty
            })

        if not artikel_list:
            await websocket.send(json.dumps({
                'type': 'admin_order_created',
                'success': False,
                'error': 'ÐÐµÑ‚ Ð²Ð°Ð»Ð¸Ð´Ð½Ñ‹Ñ… Ð¿Ð¾Ð·Ð¸Ñ†Ð¸Ð¹ Ð·Ð°ÐºÐ°Ð·Ð°'
            }))
            return

        # Ð›Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÐ°: ÐºÐ°Ðº Ñƒ Ð¾ÑÑ‚Ð°Ð»ÑŒÐ½Ñ‹Ñ… Ð·Ð°ÐºÐ°Ð·Ð¾Ð² (Ñ‡ÐµÑ€ÐµÐ· calculate_dates), Ð½Ð¾ Ñ Ð²Ð¾Ð·Ð¼Ð¾Ð¶Ð½Ð¾ÑÑ‚ÑŒÑŽ override Ð´Ð°Ñ‚Ñ‹.
        logistics_info = self.logistics_manager.calculate_dates(order_date, kunden_nr or '')
        route_id = route_id_manual or logistics_info.get('route_id', 'free')
        route_name = logistics_info.get('route_name', route_id)
        delivery_date = logistics_info.get('delivery_date', order_date)
        production_date = logistics_info.get('production_date', order_date)

        if delivery_override:
            try:
                dd = datetime.strptime(delivery_override, "%Y-%m-%d")
                delivery_date = delivery_override
                lead = int(logistics_info.get('lead_time', 1) or 1)
                production_date = (dd - timedelta(days=max(1, lead))).strftime("%Y-%m-%d")
            except Exception:
                await websocket.send(json.dumps({
                    'type': 'admin_order_created',
                    'success': False,
                    'error': f'ÐÐµÐ²ÐµÑ€Ð½Ð°Ñ Ð´Ð°Ñ‚Ð° Ð¾Ñ‚Ð³Ñ€ÑƒÐ·ÐºÐ¸: {delivery_override}'
                }))
                return

        created_at = datetime.now().isoformat()
        warehouse_id = str(payload.get('warehouse_id') or '1')
        order_data = {
            'auftrag_nr': auftrag_nr,
            'date': order_date,
            'created_at': created_at,
            'kunden_nr': kunden_nr,
            'kunde': kunde or 'Unknown',
            'address': address,
            'artikel': artikel_list,
            'status': 'pending',
            'printed': False,
            'warehouse_id': warehouse_id,
            'route_id': route_id,
            'route_name': route_name,
            'delivery_date': delivery_date,
            'production_date': production_date,
            'total_boxes': max(1, len(artikel_list) // 10 + 1),
            'source_type': source_type,
            'import_file_name': import_file_name
        }

        self.db.create_order(order_id, order_data, warehouse_id)
        self.auto_add_new_articles_from_order(order_data.get('artikel', []))
        self.db.init_order_picking(order_id, order_data['artikel'])

        await self.sessions.broadcast_to_all({
            'type': 'new_order',
            'order_id': order_id,
            'order_data': order_data
        })

        warning = ""
        if not client_found:
            warning = "ÐšÐ»Ð¸ÐµÐ½Ñ‚ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½ Ð² Ð±Ð°Ð·Ðµ Ð»Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÐ¸. Ð—Ð°ÐºÐ°Ð· ÑÐ¾Ð·Ð´Ð°Ð½, Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ ÑƒÑÑ‚Ð°Ð½Ð¾Ð²Ð»ÐµÐ½ ÐºÐ°Ðº ÑÐ²Ð¾Ð±Ð¾Ð´Ð½Ñ‹Ð¹."

        await websocket.send(json.dumps({
            'type': 'admin_order_created',
            'success': True,
            'order_id': order_id,
            'source_type': source_type,
            'import_file_name': import_file_name,
            'client_found': client_found,
            'client_missing': (not client_found),
            'kunden_nr': kunden_nr,
            'kunde': order_data.get('kunde', ''),
            'address': order_data.get('address', ''),
            'warning': warning
        }))

        logger.info(f"Admin order created: {order_id} ({len(artikel_list)} positions)")

    async def handle_delete_order(self, websocket, data):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð·"""
        order_id = data.get('order_id')

        success = self.db.delete_order(order_id)

        if success:
            # Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ Ð²ÑÐµÑ… ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
            await self.sessions.broadcast_to_all({
                'type': 'order_deleted',
                'order_id': order_id
            })

            logger.info(f"Ð£Ð´Ð°Ð»Ñ‘Ð½ Ð·Ð°ÐºÐ°Ð·: {order_id}")

    async def handle_delete_client(self, websocket, data):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð° Ð¸Ð· Ð±Ð°Ð·Ñ‹"""
        cid = data.get('client_id')
        conn = self.db.get_connection()
        try:
            conn.execute("DELETE FROM client_routes WHERE client_id = ?", (cid,))
            conn.commit()
            logger.info(f"Client deleted: {cid}")
            # Ð Ð°ÑÑÑ‹Ð»Ð°ÐµÐ¼ Ð²ÑÐµÐ¼ Ð°Ð´Ð¼Ð¸Ð½Ð°Ð¼, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ñƒ Ð½Ð¸Ñ… Ñ‚Ð¾Ð¶Ðµ Ð¸ÑÑ‡ÐµÐ·Ð»Ð¾
            await self.handle_get_all_logistics(websocket) # Ð˜Ð»Ð¸ broadcast
        except Exception as e:
            logger.error(f"Delete client error: {e}")
        finally:
            conn.close()

    async def handle_save_client_full(self, websocket, data):
        """Ð¡Ð¾Ñ…Ñ€Ð°Ð½Ð¸Ñ‚ÑŒ/ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð° Ð¿Ð¾Ð»Ð½Ð¾ÑÑ‚ÑŒÑŽ"""
        d = data.get('client_data', {})
        conn = self.db.get_connection()
        try:
            conn.execute("""
                INSERT INTO client_routes (
                    client_id, client_name, email, route_id, address, plz, city,
                    transport_type, delivery_point, monolith_client_id,
                    first_name, last_name, company_name, website_url, vat_id,
                    phone, position_title, country, price_list, discount_enabled,
                    discount_percent, payment_terms, tags, route_rules, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                client_name=excluded.client_name,
                email=excluded.email,
                route_id=excluded.route_id,
                address=excluded.address,
                plz=excluded.plz,
                city=excluded.city,
                transport_type=excluded.transport_type,
                delivery_point=excluded.delivery_point,
                monolith_client_id=excluded.monolith_client_id,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                company_name=excluded.company_name,
                website_url=excluded.website_url,
                vat_id=excluded.vat_id,
                phone=excluded.phone,
                position_title=excluded.position_title,
                country=excluded.country,
                price_list=excluded.price_list,
                discount_enabled=excluded.discount_enabled,
                discount_percent=excluded.discount_percent,
                payment_terms=excluded.payment_terms,
                tags=excluded.tags,
                route_rules=excluded.route_rules,
                updated_at=excluded.updated_at
            """, (
                d['client_id'], d['client_name'], d.get('email', ''), d['route_id'],
                d.get('address'), d.get('plz'), d.get('city'),
                d.get('transport_type'), d.get('delivery_point'),
                d.get('monolith_client_id') or None,
                d.get('first_name', ''), d.get('last_name', ''),
                d.get('company_name', ''), d.get('website_url', ''),
                d.get('vat_id', ''), d.get('phone', ''), d.get('position_title', ''),
                d.get('country', ''), d.get('price_list', ''),
                int(bool(d.get('discount_enabled'))),
                float(d.get('discount_percent') or 0),
                d.get('payment_terms', ''), d.get('tags', ''),
                d.get('route_rules', '[]'),
                datetime.now().isoformat()
            ))
            conn.commit()
            logger.info(f"Client saved: {d['client_id']}")

            # Синхронизируем маршруты в заказах клиента и шлем обновления
            updated_order_ids = self.db.update_orders_route_by_client(d['client_id'], d['route_id'])
            if updated_order_ids:
                route_name = d.get('route_id')
                try:
                    c = conn.cursor()
                    c.execute("SELECT route_name FROM logistics_routes WHERE route_id = ?", (d['route_id'],))
                    rr = c.fetchone()
                    route_name = rr['route_name'] if rr else d.get('route_id')
                except Exception:
                    pass
                for order_id in updated_order_ids:
                    await self.sessions.broadcast_to_all({
                        'type': 'order_update',
                        'order_id': order_id,
                        'update': {'route_id': d['route_id'], 'route_name': route_name}
                    })

            # Рассылаем обновленную логистику всем клиентам
            all_logistics = self.db.get_all_logistics()
            await self.sessions.broadcast_to_all({
                'type': 'logistics_data',
                'routes': all_logistics['routes'],
                'clients': all_logistics['clients']
            })
        except Exception as e:
            logger.error(f"Save client error: {e}")
        finally:
            conn.close()

    async def handle_force_print(self, websocket, data):
        """ÐŸÑ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð°Ñ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð·Ð°"""
        order_id = data.get('order_id')

        # ÐÐ°Ñ…Ð¾Ð´Ð¸Ð¼ ÑÐºÐ»Ð°Ð´ Ð´Ð»Ñ ÑÑ‚Ð¾Ð³Ð¾ Ð·Ð°ÐºÐ°Ð·Ð°
        orders = self.db.get_all_orders()
        order = next((o for o in orders if o['order_id'] == order_id), None)

        if order:
            warehouse_id = order['data'].get('warehouse_id')

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ ÐºÐ¾Ð¼Ð°Ð½Ð´Ñƒ Ð½Ð° ÑÐºÐ»Ð°Ð´
            await self.sessions.broadcast_to_warehouse(warehouse_id, {
                'type': 'force_print_order',
                'order_id': order_id,
                'order_data': order['data']
            })

            logger.info(f"ÐŸÑ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð°Ñ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð·Ð° {order_id} Ð½Ð° {warehouse_id}")

    async def handle_restart_order(self, websocket, data):
        """ÐŸÐµÑ€ÐµÐ·Ð°Ð¿ÑƒÑÑ‚Ð¸Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð·"""
        order_id = data.get('order_id')

        # Ð¡Ð±Ñ€Ð°ÑÑ‹Ð²Ð°ÐµÐ¼ ÑÑ‚Ð°Ñ‚ÑƒÑ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸
        self.db.update_order(order_id, {'printed': False, 'status': 'pending'})

        # Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ Ð²ÑÐµÑ… ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
        await self.sessions.broadcast_to_all({
            'type': 'order_update',
            'order_id': order_id,
            'update': {'printed': False, 'status': 'pending'}
        })

        logger.info(f"ÐŸÐµÑ€ÐµÐ·Ð°Ð¿ÑƒÑ‰ÐµÐ½ Ð·Ð°ÐºÐ°Ð·: {order_id}")

    async def handle_order_printed(self, websocket, data):
        """Ð—Ð°ÐºÐ°Ð· Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½"""
        order_id = data.get('order_id')

        # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ ÑÑ‚Ð°Ñ‚ÑƒÑ Ð² Ð‘Ð”
        self.db.mark_order_printed(order_id)

        # Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ Ð²ÑÐµÑ… ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
        await self.sessions.broadcast_to_all({
            'type': 'order_update',
            'order_id': order_id,
            'update': {'printed': True, 'status': 'completed'}
        })

        logger.info(f"Ð—Ð°ÐºÐ°Ð· Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½: {order_id}")

    def _normalize_article_for_match(self, article_nr: str) -> str:
        raw = str(article_nr or '').strip()
        if not raw:
            return ''
        if '-' in raw:
            raw = raw.split('-')[-1].strip()
        if raw.isdigit():
            return raw.zfill(5)
        return raw

    def _format_delivery_date_de(self, date_value: str) -> str:
        raw = str(date_value or '').strip()
        if not raw:
            return '-'
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(raw[:19], fmt).strftime("%d.%m.%Y")
            except Exception:
                continue
        return raw

    def _format_qty(self, value) -> str:
        try:
            num = float(value or 0)
        except Exception:
            return str(value or '')
        if abs(num - round(num)) < 1e-9:
            return str(int(round(num)))
        return f"{num:.2f}".rstrip('0').rstrip('.')

    def _normalize_pdf_text(self, value) -> str:
        text = str(value or '').strip()
        if not text:
            return ''

        # Попытка починить типичный mojibake (UTF-8, прочитанный как latin-1/cp1252).
        if any(token in text for token in ('Ã', 'Â', 'Ð', 'Ñ', 'â')):
            for src_enc in ('latin-1', 'cp1252'):
                try:
                    repaired = text.encode(src_enc).decode('utf-8')
                    if repaired:
                        text = repaired
                        break
                except Exception:
                    continue

        replacements = {
            'Ã„': 'Ä', 'Ã–': 'Ö', 'Ãœ': 'Ü',
            'Ã¤': 'ä', 'Ã¶': 'ö', 'Ã¼': 'ü',
            'ÃŸ': 'ß', 'â‚¬': '€',
            'â€“': '-', 'â€”': '-', '−': '-',
            '\u2018': "'", '\u2019': "'", '\u201c': '"', '\u201d': '"',
            'Stra´e': 'Straße', 'Stra`e': 'Straße', "Stra'e": 'Straße',
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)

        return text

    def _get_freeze_articles_set(self) -> Set[str]:
        freeze_articles: Set[str] = set()
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT article_nr
                    FROM recipes
                    WHERE lower(trim(COALESCE(freeze_mode, ''))) = 'tiefkuhle'
                """)
                for row in cursor.fetchall():
                    art = self._normalize_article_for_match(row['article_nr'])
                    if art:
                        freeze_articles.add(art)
        except Exception as exc:
            logger.warning(f"[ORDER EMAIL] Failed to load freeze articles: {exc}")
        return freeze_articles

    def _build_customer_shipping_rows(self, order_data: dict) -> List[Tuple[str, str, str, str, str]]:
        artikel_list = order_data.get('artikel', []) or []
        freeze_set = self._get_freeze_articles_set()
        rows: List[Tuple[str, str, str, str, str]] = []

        try:
            sorted_artikel = sorted(artikel_list, key=lambda x: int(float(x.get('pos', 99999) or 99999)))
        except Exception:
            sorted_artikel = artikel_list

        for idx, art in enumerate(sorted_artikel, start=1):
            art_nr_raw = art.get('artikel_nr') or art.get('nummer') or ''
            art_nr = self._normalize_pdf_text(art_nr_raw)
            art_norm = self._normalize_article_for_match(art_nr)
            name = self._normalize_pdf_text(art.get('beschreibung') or art.get('name') or '')
            try:
                picked_qty = float(art.get('picked', art.get('picked_qty', 0)) or 0)
            except Exception:
                picked_qty = 0.0
            try:
                order_qty = float(art.get('menge', 0) or 0)
            except Exception:
                order_qty = 0.0
            is_checked = bool(art.get('checked'))

            # В клиентский Auftrag попадают только позиции,
            # явно отмеченные складом как отгруженные.
            if not is_checked:
                continue

            qty_value = picked_qty if picked_qty > 0 else order_qty
            if qty_value <= 0:
                continue
            qty = self._format_qty(qty_value)

            base_comment = str(
                art.get('comment')
                or art.get('kommentar')
                or art.get('notes')
                or ''
            ).strip()
            comments = []
            if base_comment:
                comments.append(base_comment)
            if art_norm in freeze_set:
                comments.append("Tiefkuhle")
            comment_text = self._normalize_pdf_text(" | ".join(comments))

            pos_value = art.get('pos')
            rows.append((str(pos_value if pos_value not in (None, '') else idx), art_nr, name, qty, comment_text))

        return rows

    def _cleanup_old_customer_shipping_pdfs(self, out_dir: Path, keep_days: int = 7) -> None:
        """Удаляет customer shipping PDF старше keep_days дней."""
        try:
            if not out_dir.exists():
                return
            cutoff_ts = (datetime.now() - timedelta(days=max(1, int(keep_days)))).timestamp()
            removed = 0
            for p in out_dir.glob("*.pdf"):
                try:
                    if p.is_file() and p.stat().st_mtime < cutoff_ts:
                        p.unlink(missing_ok=True)
                        removed += 1
                except Exception as e:
                    logger.warning(f"[ORDER EMAIL] Cannot remove old PDF {p}: {e}")
            if removed:
                logger.info(f"[ORDER EMAIL] Cleaned old customer shipping PDFs: {removed} (>{keep_days} days)")
        except Exception as e:
            logger.warning(f"[ORDER EMAIL] Cleanup old customer shipping PDFs failed: {e}")

    def _build_customer_shipping_pdf(self, order_id: str, order_data: dict, boxes_count: int) -> Path:
        out_dir = Path(__file__).parent / "generated" / "customer_shipping_pdfs"
        out_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_old_customer_shipping_pdfs(out_dir, keep_days=7)

        order_no = self._normalize_pdf_text(order_data.get('auftrag_nr') or order_id or '')
        safe_no = ''.join(ch for ch in order_no if ch.isalnum() or ch in ('-', '_')) or "order"
        pdf_path = out_dir / f"Versand_{safe_no}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        kunde = self._normalize_pdf_text(order_data.get('kunde') or '') or "-"
        address = self._normalize_pdf_text(order_data.get('address') or '') or "-"
        versand_date = datetime.now().strftime("%d.%m.%Y")
        rows = self._build_customer_shipping_rows(order_data)
        actual_rows_count = len(rows)
        total_qty = 0.0
        for _p, _a, _n, qty, _c in rows:
            try:
                total_qty += float(qty)
            except Exception:
                continue
        if not rows:
            rows = [("-", "-", "Keine Positionen ausgewaehlt", "-", "-")]

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.pdfgen import canvas

            c = canvas.Canvas(str(pdf_path), pagesize=A4)
            page_w, page_h = A4
            y = page_h - 42

            # Компактная шапка: слева заголовок, справа логотип.
            c.setFont("Helvetica-Bold", 16)
            c.drawString(40, y, "Versandliste")
            logo_path = Path(__file__).parent / "logo_Monolith_Bakery.png"
            if logo_path.exists():
                try:
                    from reportlab.lib.utils import ImageReader
                    logo = ImageReader(str(logo_path))
                    logo_w = 220
                    logo_h = 36
                    c.drawImage(logo, page_w - 40 - logo_w, y - 18, width=logo_w, height=logo_h, preserveAspectRatio=True, mask='auto')
                except Exception:
                    pass
            c.line(40, y - 24, page_w - 35, y - 24)
            y -= 42

            # Блок реквизитов: жирные подписи + обычные значения.
            meta_lines = [
                ("Bestellnummer:", order_no),
                ("Kunde:", kunde),
                ("Adresse:", address),
                ("Versanddatum:", versand_date),
                ("Anzahl Kartons:", str(int(boxes_count or 0))),
                ("Positionen / Gesamtmenge:", f"{actual_rows_count} / {self._format_qty(total_qty)}"),
            ]
            for label, value in meta_lines:
                c.setFont("Helvetica-Bold", 10)
                c.drawString(40, y, label)
                c.setFont("Helvetica", 10)
                c.drawString(205, y, self._normalize_pdf_text(value))
                y -= 15
            y -= 6

            table_x = 40
            table_w = page_w - 75
            col_w = [42, 82, 255, 70, table_w - (42 + 82 + 255 + 70)]
            row_h = 15
            grid_col = colors.HexColor("#BFC5CF")
            header_fill = colors.HexColor("#EFF2F7")
            text_col = colors.HexColor("#1F2937")

            def _draw_table_header(y_top: float) -> float:
                c.setStrokeColor(grid_col)
                c.setLineWidth(0.8)
                c.setFillColor(header_fill)
                c.rect(table_x, y_top - row_h, table_w, row_h, stroke=1, fill=1)

                headers = ["Pos", "Artikel", "Bezeichnung", "Menge", "Kommentar"]
                cx = table_x
                c.setFont("Helvetica-Bold", 9)
                c.setFillColor(text_col)
                for i, head in enumerate(headers):
                    c.drawString(cx + 4, y_top - 11, head)
                    cx += col_w[i]
                    if i < len(headers) - 1:
                        c.line(cx, y_top - row_h, cx, y_top)
                return y_top - row_h

            y = _draw_table_header(y)

            c.setFont("Helvetica", 8.7)
            c.setFillColor(text_col)
            for pos, art_nr, name, qty, comment in rows:
                if y < 62:
                    c.showPage()
                    y = page_h - 45

                    c.setFont("Helvetica-Bold", 13)
                    c.drawString(40, y, f"Versandliste (Fortsetzung) - {order_no}")
                    c.setStrokeColor(colors.HexColor("#D3D8E2"))
                    c.setLineWidth(0.8)
                    c.line(40, y - 8, page_w - 35, y - 8)
                    y -= 18

                    c.setFont("Helvetica-Bold", 9)
                    c.setFillColor(text_col)
                    c.drawString(40, y, "Positionen / Gesamtmenge:")
                    c.setFont("Helvetica", 9)
                    c.drawString(165, y, f"{actual_rows_count} / {self._format_qty(total_qty)}")
                    y -= 12

                    y = _draw_table_header(y)
                    c.setFont("Helvetica-Bold", 9)
                    c.setFillColor(text_col)
                    c.setFont("Helvetica", 8.7)

                # Строка таблицы: светлые границы, читаемая сетка.
                y_bottom = y - row_h
                c.setStrokeColor(grid_col)
                c.setLineWidth(0.5)
                c.rect(table_x, y_bottom, table_w, row_h, stroke=1, fill=0)

                cx = table_x
                cell_values = [str(pos), str(art_nr), str(name), str(qty), str(comment)]
                clip_lens = [5, 16, 54, 12, 34]
                for i, val in enumerate(cell_values):
                    txt = self._normalize_pdf_text(val)[:clip_lens[i]]
                    if i == 3:
                        c.drawRightString(cx + col_w[i] - 4, y_bottom + 4, txt)
                    else:
                        c.drawString(cx + 4, y_bottom + 4, txt)
                    cx += col_w[i]
                    if i < len(cell_values) - 1:
                        c.line(cx, y_bottom, cx, y)

                y = y_bottom

            c.save()
            return pdf_path
        except Exception as reportlab_exc:
            logger.warning(f"[ORDER EMAIL] ReportLab unavailable, fallback PDF builder: {reportlab_exc}")

        try:
            from PIL import Image, ImageDraw, ImageFont

            def _load_font(size: int, bold: bool = False):
                candidates = (
                    ["arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"]
                    if bold else
                    ["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"]
                )
                for name in candidates:
                    try:
                        return ImageFont.truetype(name, size=size)
                    except Exception:
                        continue
                return ImageFont.load_default()

            def _clip_text(draw_obj, text: str, font_obj, max_width: int) -> str:
                val = self._normalize_pdf_text(text)
                while val and draw_obj.textlength(val, font=font_obj) > max_width:
                    val = val[:-1]
                return val

            font_title = _load_font(36, bold=True)
            font_meta = _load_font(16, bold=False)
            font_meta_b = _load_font(16, bold=True)
            font_head = _load_font(16, bold=True)
            font_row = _load_font(15, bold=False)
            font_footer = _load_font(13, bold=False)

            page_w, page_h = 1240, 1754  # A4 ~150dpi
            margin = 52
            row_h = 34
            table_x = margin
            table_w = page_w - margin * 2
            col_w = [72, 150, 560, 120, table_w - (72 + 150 + 560 + 120)]

            actual_rows_count = len(rows)
            total_qty = 0.0
            for _p, _a, _n, qty, _c in rows:
                try:
                    total_qty += float(qty)
                except Exception:
                    continue

            logo_img = None
            logo_path = Path(__file__).parent / "logo_Monolith_Bakery.png"
            if logo_path.exists():
                try:
                    logo_img = Image.open(logo_path).convert("RGBA")
                except Exception:
                    logo_img = None

            if not rows:
                rows = [("-", "-", "Keine Positionen ausgewaehlt", "-", "-")]

            table_header_h = row_h
            header_h = 98
            meta_line_h = 24
            meta_lines_count = 6
            meta_block_h = meta_line_h * meta_lines_count + 12
            top_h = margin + header_h + 12 + meta_block_h + table_header_h
            usable_h = page_h - top_h - 86
            rows_per_page = max(10, usable_h // row_h)
            row_pages = [rows[i:i + rows_per_page] for i in range(0, len(rows), rows_per_page)]

            images = []
            for page_idx, page_rows in enumerate(row_pages, start=1):
                img = Image.new("RGB", (page_w, page_h), "white")
                draw = ImageDraw.Draw(img)

                y = margin
                header_top = y
                header_bottom = y + header_h

                # Левая часть шапки: название документа
                draw.text((margin, header_top + 26), "Versandliste", font=font_title, fill="black")

                # Правая часть шапки: фирменный логотип
                if logo_img:
                    max_logo_w = 520
                    max_logo_h = 86
                    ratio = min(max_logo_w / logo_img.width, max_logo_h / logo_img.height)
                    logo_w = max(1, int(logo_img.width * ratio))
                    logo_h_draw = max(1, int(logo_img.height * ratio))
                    resized_logo = logo_img.resize((logo_w, logo_h_draw))
                    logo_x = page_w - margin - logo_w
                    logo_y = header_top + max(0, (header_h - logo_h_draw) // 2)
                    img.paste(resized_logo, (logo_x, logo_y), resized_logo)

                draw.line((margin, header_bottom, page_w - margin, header_bottom), fill="#333333", width=2)
                y = header_bottom + 12

                # Блок метаданных
                meta_lines = [
                    ("Bestellnummer:", order_no),
                    ("Kunde:", kunde),
                    ("Adresse:", address),
                    ("Versanddatum:", versand_date),
                    ("Anzahl Kartons:", str(int(boxes_count or 0))),
                    ("Positionen / Gesamtmenge:", f"{actual_rows_count} / {self._format_qty(total_qty)}"),
                ]
                for label, value in meta_lines:
                    draw.text((margin, y), label, font=font_meta_b, fill="black")
                    draw.text((margin + 255, y), self._normalize_pdf_text(value), font=font_meta, fill="black")
                    y += meta_line_h

                y += 10

                # Таблица: шапка
                x = table_x
                draw.rectangle((table_x, y, table_x + table_w, y + table_header_h), outline="black", fill="#EDEDED", width=2)
                headers = ["Pos", "Artikel", "Bezeichnung", "Menge", "Kommentar"]
                for i, head in enumerate(headers):
                    draw.text((x + 8, y + 8), head, font=font_head, fill="black")
                    x += col_w[i]
                    if i < len(headers) - 1:
                        draw.line((x, y, x, y + table_header_h), fill="black", width=2)

                y += table_header_h

                # Таблица: строки
                for pos, art_nr, name, qty, comment in page_rows:
                    draw.rectangle((table_x, y, table_x + table_w, y + row_h), outline="black", width=1)
                    x = table_x
                    cell_values = [pos, art_nr, name, qty, comment]
                    for i, val in enumerate(cell_values):
                        max_text_w = col_w[i] - 12
                        clipped = _clip_text(draw, val, font_row, max_text_w)
                        if i == 3:
                            text_w = draw.textlength(clipped, font=font_row)
                            draw.text((x + col_w[i] - text_w - 7, y + 8), clipped, font=font_row, fill="black")
                        else:
                            draw.text((x + 6, y + 8), clipped, font=font_row, fill="black")
                        x += col_w[i]
                        if i < len(cell_values) - 1:
                            draw.line((x, y, x, y + row_h), fill="black", width=1)
                    y += row_h

                footer = f"Seite {page_idx} / {len(row_pages)}"
                fw = draw.textlength(footer, font=font_footer)
                draw.text((page_w - margin - fw, page_h - margin), footer, font=font_footer, fill="#444444")

                images.append(img)

            if images:
                first_page, rest_pages = images[0], images[1:]
                first_page.save(str(pdf_path), "PDF", resolution=150.0, save_all=True, append_images=rest_pages)
                return pdf_path
        except Exception as pillow_exc:
            logger.warning(f"[ORDER EMAIL] Pillow fallback failed, using basic PDF builder: {pillow_exc}")

        # Экстренный fallback без внешних библиотек
        def _pdf_escape_winansi(text: str) -> str:
            clean = self._normalize_pdf_text(text)
            raw = clean.encode('cp1252', errors='replace')
            raw = raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            return raw.decode('latin-1')

        lines = [
            "Versandliste",
            f"Bestellnummer: {order_no}",
            f"Kunde: {kunde}",
            f"Adresse: {address}",
            f"Versanddatum: {versand_date}",
            f"Anzahl Kartons: {int(boxes_count or 0)}",
            "",
        ]
        for pos, art_nr, name, qty, comment in rows:
            lines.append(f"{pos} | {art_nr} | {name} | {qty} | {comment}")

        stream = "BT\n/F1 10 Tf\n40 800 Td\n12 TL\n" + "\n".join(
            [f"({_pdf_escape_winansi(x)}) Tj\nT*" for x in lines]
        ) + "\nET"

        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4\n")
            obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            obj2 = b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [4 0 R] >>\nendobj\n"
            obj3 = b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
            obj4 = b"4 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>\nendobj\n"
            obj5 = f"5 0 obj\n<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream\nendobj\n".encode("latin-1")
            objects = [obj1, obj2, obj3, obj4, obj5]
            offsets = [0]
            for ob in objects:
                offsets.append(f.tell())
                f.write(ob)
            xref_pos = f.tell()
            f.write(f"xref\n0 {len(objects)+1}\n".encode("ascii"))
            f.write(b"0000000000 65535 f \n")
            for off in offsets[1:]:
                f.write(f"{off:010d} 00000 n \n".encode("ascii"))
            trailer = f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
            f.write(trailer.encode("ascii"))

        return pdf_path

    def _resolve_order_customer_email(self, order_data: dict) -> str:
        """Определить email клиента из заказа, с fallback в client_routes."""
        direct_email = str(
            order_data.get('email')
            or order_data.get('e_mail')
            or order_data.get('mail')
            or order_data.get('kunde_email')
            or order_data.get('customer_email')
            or ''
        ).strip()
        if '@' not in direct_email:
            direct_email = ''

        kunden_raw = str(order_data.get('kunden_nr') or '').strip()
        kunden_norm = kunden_raw.lstrip('0') or kunden_raw
        logistics_email = ''

        if kunden_raw:
            try:
                logistics = self.db.get_all_logistics() or {}
                for c in logistics.get('clients', []) or []:
                    cid = str(c.get('client_id') or '').strip()
                    mid = str(c.get('monolith_client_id') or '').strip()
                    cid_norm = cid.lstrip('0') or cid
                    mid_norm = mid.lstrip('0') or mid
                    if kunden_raw in (cid, mid) or kunden_norm in (cid_norm, mid_norm):
                        email = str(c.get('email') or '').strip()
                        if '@' in email:
                            logistics_email = email
                            break
            except Exception as e:
                logger.warning(f"[ORDER EMAIL] Failed to resolve client email from logistics: {e}")

        # ВАЖНО: приоритет у актуального email из логистики.
        return logistics_email or direct_email

    def _send_customer_shipping_email(self, order_id: str, order_data: dict, pdf_path: Path) -> Tuple[bool, str, str]:
        kunde = str(order_data.get('kunde') or '').strip() or "-"
        order_no = str(order_data.get('auftrag_nr') or order_id or '').strip()
        client_email = self._resolve_order_customer_email(order_data)

        # Отправка всегда клиенту (без тестового override).
        to_email = client_email
        if not to_email:
            return False, "", "recipient_not_set"

        smtp_host = ORDER_EMAIL_CONFIG['smtp_host']
        smtp_port = ORDER_EMAIL_CONFIG['smtp_port']
        smtp_user = ORDER_EMAIL_CONFIG['smtp_user']
        smtp_password = ORDER_EMAIL_CONFIG['smtp_password']
        from_email = ORDER_EMAIL_CONFIG['from_email'] or smtp_user

        if not smtp_host or not from_email:
            return False, to_email, "smtp_not_configured"

        msg = EmailMessage()
        msg['Subject'] = f"Versandliste Bestellung {order_no}"
        msg['From'] = from_email
        msg['To'] = to_email
        msg.set_content(
            "Sehr geehrte Damen und Herren,\n\n"
            f"anbei übersenden wir Ihnen die Versandliste zur Bestellung {order_no} für {kunde}.\n"
            "Für Rückfragen stehen wir Ihnen jederzeit gerne zur Verfügung.\n\n"
            "Mit freundlichen Grüßen\nMonolith Bakery & Confectionery"
        )

        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        mime_type, _ = mimetypes.guess_type(str(pdf_path))
        if not mime_type:
            mime_type = "application/pdf"
        main_type, sub_type = mime_type.split("/", 1)
        msg.add_attachment(pdf_bytes, maintype=main_type, subtype=sub_type, filename=pdf_path.name)

        def _build_smtp_tls_context() -> ssl.SSLContext:
            ctx = ssl.create_default_context()

            # Test-only escape hatch for problematic local trust stores.
            if not ORDER_EMAIL_CONFIG.get('smtp_tls_verify', True):
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                return ctx

            # Prefer certifi CA bundle on Windows/embedded Python installs.
            try:
                import certifi  # type: ignore
                cafile = certifi.where()
                if cafile:
                    ctx.load_verify_locations(cafile=cafile)
            except Exception:
                pass
            return ctx

        tls_ctx = _build_smtp_tls_context()

        def _send_with_context(ctx: ssl.SSLContext):
            if ORDER_EMAIL_CONFIG['smtp_ssl']:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30, context=ctx) as smtp:
                    if smtp_user and smtp_password:
                        smtp.login(smtp_user, smtp_password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
                    if ORDER_EMAIL_CONFIG['smtp_starttls']:
                        smtp.starttls(context=ctx)
                    if smtp_user and smtp_password:
                        smtp.login(smtp_user, smtp_password)
                    smtp.send_message(msg)

        try:
            _send_with_context(tls_ctx)
        except ssl.SSLCertVerificationError:
            # Last-resort fallback for Windows hosts with broken CA store.
            insecure_ctx = ssl.create_default_context()
            insecure_ctx.check_hostname = False
            insecure_ctx.verify_mode = ssl.CERT_NONE
            logger.warning("[ORDER EMAIL] TLS verify failed, retrying with TLS verification disabled")
            _send_with_context(insecure_ctx)

        return True, to_email, ""

    def _process_boxes_email_notification(self, order_id: str, boxes_count: int) -> dict:
        order_data = self.db.get_order(order_id) or {}
        if not order_data:
            return {'success': False, 'recipient': '', 'error': 'order_not_found'}

        kunde = str(order_data.get('kunde') or '').strip() or "-"
        order_no = str(order_data.get('auftrag_nr') or order_id or '').strip()
        subject = f"Versandliste Bestellung {order_no}"
        body = (
            "Sehr geehrte Damen und Herren,\n\n"
            f"anbei übersenden wir Ihnen die Versandliste zur Bestellung {order_no} für {kunde}.\n"
            "Für Rückfragen stehen wir Ihnen jederzeit gerne zur Verfügung.\n\n"
            "Mit freundlichen Grüßen\nMonolith Bakery & Confectionery"
        )
        pdf_path = self._build_customer_shipping_pdf(order_id, order_data, boxes_count)
        success, recipient, error = self._send_customer_shipping_email(order_id, order_data, pdf_path)
        return {
            'success': success,
            'recipient': recipient,
            'error': error,
            'pdf_path': str(pdf_path),
            'subject': subject,
            'body': body,
            'sent_at': datetime.now().isoformat()
        }

    async def handle_get_customer_shipping_doc(self, websocket, data):
        order_id = str(data.get('order_id') or '').strip()
        if not order_id:
            await self.safe_send(websocket, {
                'type': 'customer_shipping_doc_data',
                'success': False,
                'error': 'order_id_missing'
            })
            return

        order_data = self.db.get_order(order_id) or {}
        if not order_data:
            await self.safe_send(websocket, {
                'type': 'customer_shipping_doc_data',
                'success': False,
                'order_id': order_id,
                'error': 'order_not_found'
            })
            return

        try:
            box_int = int(float(data.get('boxes_count') or order_data.get('boxes_count') or 0))
        except Exception:
            box_int = 0
        versand_date = datetime.now().strftime("%d.%m.%Y")

        def _prepare_doc_payload():
            pdf_path = self._build_customer_shipping_pdf(order_id, order_data, box_int)
            with open(pdf_path, 'rb') as f:
                pdf_b64 = base64.b64encode(f.read()).decode('ascii')
            rows = self._build_customer_shipping_rows(order_data)
            return str(pdf_path), pdf_b64, rows

        try:
            pdf_path, pdf_b64, rows = await asyncio.to_thread(_prepare_doc_payload)
            await self.safe_send(websocket, {
                'type': 'customer_shipping_doc_data',
                'success': True,
                'order_id': order_id,
                'order_no': str(order_data.get('auftrag_nr') or order_id or '').strip(),
                'kunde': str(order_data.get('kunde') or '').strip() or "-",
                'address': str(order_data.get('address') or '').strip() or "-",
                'versand_date': versand_date,
                'delivery_date': versand_date,
                'boxes_count': box_int,
                'rows': rows,
                'pdf_name': Path(pdf_path).name,
                'pdf_base64': pdf_b64
            })
        except Exception as exc:
            logger.error(f"[ORDER DOC] Failed to prepare preview for {order_id}: {exc}")
            await self.safe_send(websocket, {
                'type': 'customer_shipping_doc_data',
                'success': False,
                'order_id': order_id,
                'error': str(exc)
            })

    def _extract_invoice_file_candidates(self, order_id: str, order_data: dict, requested_name: str = '') -> list[str]:
        seen = set()
        candidates = []

        def add_candidate(raw_value):
            value = str(raw_value or '').strip()
            if not value:
                return
            name = Path(value.replace('\\', '/')).name
            if not name:
                return
            if not name.lower().endswith('.pdf'):
                name = f"{name}.pdf"
            key = name.lower()
            if key in seen:
                return
            seen.add(key)
            candidates.append(name)

        add_candidate(requested_name)
        add_candidate(order_data.get('invoice_file'))

        invoice_status = str(order_data.get('invoice_status') or '').strip()
        invoice_status = re.sub(r'^[^0-9A-Za-z]+', '', invoice_status).strip()
        add_candidate(invoice_status)
        for key in ('invoice_number', 'invoice_no', 'rechnung_nr', 'invoice_id'):
            add_candidate(order_data.get(key))

        fallback_order = str(order_id or '').strip()
        if fallback_order:
            add_candidate(fallback_order)
        return candidates

    def _find_invoice_file_for_order(self, order_id: str, order_data: dict, requested_name: str = ''):
        base_dir = Path(RECHNUNG_OUTPUT_FOLDER)
        candidates = self._extract_invoice_file_candidates(order_id, order_data, requested_name)

        for candidate in candidates:
            candidate_path = base_dir / Path(candidate).name
            try:
                if candidate_path.is_file():
                    return candidate_path
            except Exception:
                continue

        for candidate in candidates:
            stem = Path(candidate).stem.strip()
            if not stem:
                continue
            for pattern in (f"{stem}.pdf", f"{stem}_*.pdf"):
                try:
                    matches = sorted(p for p in base_dir.glob(pattern) if p.is_file())
                except Exception:
                    matches = []
                if matches:
                    return matches[0]
        return None

    async def handle_download_invoice_file(self, websocket, data):
        order_id = str(data.get('order_id') or '').strip()
        requested_name = str(data.get('invoice_file') or data.get('invoice_number') or '').strip()
        if not order_id:
            await self.safe_send(websocket, {
                'type': 'invoice_file_error',
                'message': 'order_id_missing'
            })
            return

        order_data = self.db.get_order(order_id) or {}
        if not order_data:
            await self.safe_send(websocket, {
                'type': 'invoice_file_error',
                'order_id': order_id,
                'message': 'order_not_found'
            })
            return

        invoice_path = await asyncio.to_thread(self._find_invoice_file_for_order, order_id, order_data, requested_name)
        if not invoice_path:
            await self.safe_send(websocket, {
                'type': 'invoice_file_error',
                'order_id': order_id,
                'message': 'invoice_file_not_found'
            })
            return

        try:
            raw = await asyncio.to_thread(invoice_path.read_bytes)
            await self.safe_send(websocket, {
                'type': 'invoice_file_data',
                'order_id': order_id,
                'file_name': invoice_path.name,
                'file_data_b64': base64.b64encode(raw).decode('ascii')
            })
        except Exception as exc:
            logger.error(f"[INVOICE] Failed to read invoice for {order_id}: {exc}")
            await self.safe_send(websocket, {
                'type': 'invoice_file_error',
                'order_id': order_id,
                'message': str(exc)
            })

    async def handle_boxes_info(self, websocket, data):
        """Ð˜Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸Ñ Ð¾ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ°Ñ… Ð¾Ñ‚ ÑÐºÐ»Ð°Ð´Ð°"""
        order_id = data.get('order_id')
        boxes_count = data.get('boxes_count')
        kunde = data.get('kunde')
        address = data.get('address')
        date = data.get('date')
        lieferschein = data.get('lieferschein')

        logger.info(f"[BOXES] ÐŸÐ¾Ð»ÑƒÑ‡ÐµÐ½Ñ‹ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¾ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ°Ñ… Ð´Ð»Ñ {order_id}: {boxes_count} ÑˆÑ‚")

        # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÑŽ Ð¾ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ°Ñ… Ð² Ð·Ð°ÐºÐ°Ð·.
        # Ð•ÑÐ»Ð¸ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ¸ > 0, ÑÑ‡Ð¸Ñ‚Ð°ÐµÐ¼, Ñ‡Ñ‚Ð¾ Ð¿ÐµÑ‡Ð°Ñ‚ÑŒ Ð¿Ð¾ Ð·Ð°ÐºÐ°Ð·Ñƒ Ð²Ñ‹Ð¿Ð¾Ð»Ð½ÐµÐ½Ð°.
        try:
            box_int = int(float(boxes_count or 0))
        except Exception:
            box_int = 0

        update_payload = {
            'boxes_count': box_int,
            'boxes_date': date
        }
        if box_int > 0:
            update_payload['printed'] = True
            update_payload['status'] = 'completed'

        self.db.update_order(order_id, update_payload)
        # Программная верификация: сразу читаем из БД и сверяем.
        saved_box_int = None
        verify_ok = False
        try:
            saved_order = self.db.get_order(order_id) or {}
            saved_box_int = int(float(saved_order.get('boxes_count') or 0))
            verify_ok = (saved_box_int == box_int)
            logger.info(
                f"[BOXES_VERIFY] order={order_id} requested={box_int} saved={saved_box_int} ok={verify_ok}"
            )
        except Exception as verify_exc:
            logger.warning(f"[BOXES_VERIFY] Failed for {order_id}: {verify_exc}")

        email_result = None
        if box_int > 0:
            try:
                email_result = await asyncio.to_thread(self._process_boxes_email_notification, order_id, box_int)
                if email_result.get('success'):
                    logger.info(
                        f"[ORDER EMAIL] Sent shipment PDF for {order_id} to {email_result.get('recipient')} "
                        f"({email_result.get('pdf_path')})"
                    )
                else:
                    logger.warning(
                        f"[ORDER EMAIL] Not sent for {order_id}: {email_result.get('error')} "
                        f"(recipient={email_result.get('recipient') or '-'})"
                    )
            except Exception as email_exc:
                email_result = {'success': False, 'recipient': '', 'error': str(email_exc)}
                logger.error(f"[ORDER EMAIL] Error for {order_id}: {email_exc}")

        if email_result is not None:
            email_update = {
                'customer_email_sent': bool(email_result.get('success')),
                'customer_email_recipient': str(email_result.get('recipient') or ''),
                'customer_email_subject': str(email_result.get('subject') or ''),
                'customer_email_body': str(email_result.get('body') or ''),
                'customer_email_error': str(email_result.get('error') or ''),
            }
            if email_result.get('success') and email_result.get('sent_at'):
                email_update['customer_email_sent_at'] = str(email_result.get('sent_at'))
            self.db.update_order(order_id, email_update)
        logger.info(f"[BOXES] Ð”Ð°Ð½Ð½Ñ‹Ðµ ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ñ‹ Ð² Ð‘Ð” Ð´Ð»Ñ {order_id}")

        # Ð¢Ñ€Ð°Ð½ÑÐ»Ð¸Ñ€ÑƒÐµÐ¼ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÑŽ Ð¾Ð¿ÐµÑ€Ð°Ñ‚Ð¾Ñ€Ñƒ Ð¸ Ð°Ð´Ð¼Ð¸Ð½Ñƒ
        admin_count = len(self.sessions.admin_clients)
        operator_count = len(self.sessions.operator_clients)
        logger.info(f"[BOXES] Ð Ð°ÑÑÑ‹Ð»ÐºÐ° ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ: Ð°Ð´Ð¼Ð¸Ð½Ð¾Ð²={admin_count}, Ð¾Ð¿ÐµÑ€Ð°Ñ‚Ð¾Ñ€Ð¾Ð²={operator_count}")

        await self.sessions.broadcast_to_admins({
            'type': 'boxes_info',
            'order_id': order_id,
            'boxes_count': box_int,
            'printed': True if box_int > 0 else False,
            'kunde': kunde,
            'address': address,
            'date': date,
            'lieferschein': lieferschein
        })

        await self.sessions.broadcast_to_operators({
            'type': 'boxes_info',
            'order_id': order_id,
            'boxes_count': box_int,
            'printed': True if box_int > 0 else False,
            'kunde': kunde,
            'address': address,
            'date': date,
            'lieferschein': lieferschein
        })

        if email_result is not None:
            await self.safe_send(websocket, {
                'type': 'customer_shipping_email_result',
                'order_id': order_id,
                'success': bool(email_result.get('success')),
                'recipient': email_result.get('recipient', ''),
                'error': email_result.get('error', ''),
                'subject': email_result.get('subject', ''),
                'body': email_result.get('body', ''),
                'sent_at': email_result.get('sent_at', '')
            })

        # Подтверждение отправителю: значение реально сохранено в БД.
        await self.safe_send(websocket, {
            'type': 'boxes_info_saved',
            'order_id': order_id,
            'requested_boxes_count': box_int,
            'saved_boxes_count': saved_box_int if saved_box_int is not None else box_int,
            'verify_ok': bool(verify_ok) if saved_box_int is not None else True,
        })


        logger.info(f"[BOXES] âœ… Ð¡Ð¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¾ Ð´Ð»Ñ {order_id}")
        logger.info(f"Ð˜Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸Ñ Ð¾ ÐºÐ¾Ñ€Ð¾Ð±ÐºÐ°Ñ… Ð´Ð»Ñ Ð·Ð°ÐºÐ°Ð·Ð° {order_id}: {boxes_count} ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº")

    async def handle_labels_printed(self, websocket, data):
        """Ð˜Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸Ñ Ð¾ Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½Ð½Ñ‹Ñ… Ð»ÐµÐ¹Ð±Ð»Ð°Ñ… Ð¾Ñ‚ ÑÐºÐ»Ð°Ð´Ð°"""
        order_id = data.get('order_id')
        labels = data.get('labels', [])
        label_language = data.get('label_language', '')

        logger.info(f"[LABELS] ÐŸÐ¾Ð»ÑƒÑ‡ÐµÐ½Ñ‹ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¾ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ Ð´Ð»Ñ {order_id}: {len(labels)} Ð°Ñ€Ñ‚Ð¸ÐºÐ»Ð¾Ð²")

        # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÑŽ Ð¾ Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½Ð½Ñ‹Ñ… Ð»ÐµÐ¹Ð±Ð»Ð°Ñ… Ð² Ð·Ð°ÐºÐ°Ð·
        self.db.update_order(order_id, {
            'printed': True,  # Ð¤Ð»Ð°Ð³ Ñ‡Ñ‚Ð¾ Ð»ÐµÐ¹Ð±Ð»Ñ‹ Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½Ñ‹
            'labels_printed': len(labels),
            'labels_data': labels,  # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ ÐºÐ°Ðº Ð¼Ð°ÑÑÐ¸Ð², Ð½Ðµ JSON ÑÑ‚Ñ€Ð¾ÐºÑƒ
            'label_language': label_language
        })
        logger.info(f"[LABELS] Ð”Ð°Ð½Ð½Ñ‹Ðµ ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ñ‹ Ð² Ð‘Ð” Ð´Ð»Ñ {order_id}")

        # Ð¢Ñ€Ð°Ð½ÑÐ»Ð¸Ñ€ÑƒÐµÐ¼ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÑŽ Ð°Ð´Ð¼Ð¸Ð½Ð¸ÑÑ‚Ñ€Ð°Ñ‚Ð¾Ñ€Ñƒ Ð¸ Ð¾Ð¿ÐµÑ€Ð°Ñ‚Ð¾Ñ€Ñƒ
        broadcast_data = {
            'type': 'labels_printed',
            'order_id': order_id,
            'labels': labels,
            'label_language': label_language,
            'printed': True,
            'labels_printed': len(labels)
        }

        # Ð›Ð¾Ð³Ð¸Ñ€ÑƒÐµÐ¼ ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð½Ñ‹Ñ… ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
        admin_count = len(self.sessions.admin_clients)
        operator_count = len(self.sessions.operator_clients)
        logger.info(f"[LABELS] Ð Ð°ÑÑÑ‹Ð»ÐºÐ° ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ñ: Ð°Ð´Ð¼Ð¸Ð½Ð¾Ð²={admin_count}, Ð¾Ð¿ÐµÑ€Ð°Ñ‚Ð¾Ñ€Ð¾Ð²={operator_count}")

        if admin_count == 0:
            logger.warning(f"[LABELS] âš ï¸ ÐÐµÑ‚ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð½Ñ‹Ñ… Ð°Ð´Ð¼Ð¸Ð½Ð¸ÑÑ‚Ñ€Ð°Ñ‚Ð¾Ñ€Ð¾Ð²!")

        await self.sessions.broadcast_to_admins(broadcast_data)
        await self.sessions.broadcast_to_operators(broadcast_data)

        logger.info(f"[LABELS] âœ… Ð¡Ð¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð¾ Ð´Ð»Ñ {order_id}")
        logger.info(f"ÐÐ°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð½Ñ‹ Ð»ÐµÐ¹Ð±Ð»Ñ‹ Ð´Ð»Ñ Ð·Ð°ÐºÐ°Ð·Ð° {order_id}: {len(labels)} Ð°Ñ€Ñ‚Ð¸ÐºÐ»Ð¾Ð² ({label_language})")

    async def handle_add_print_history(self, websocket, data):
        """Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð·Ð°Ð¿Ð¸ÑÑŒ Ð² Ð¸ÑÑ‚Ð¾Ñ€Ð¸ÑŽ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸"""
        order_id = data.get('order_id')
        label_language = data.get('label_language')
        boxes_count = data.get('boxes_count')

        # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÑŽ Ð¾ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ðµ Ð¸Ð· ÑÐµÑÑÐ¸Ð¸
        session = self.sessions.get_session(websocket)
        if not session:
            logger.warning(f"ÐŸÐ¾Ð¿Ñ‹Ñ‚ÐºÐ° Ð´Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð¸ÑÑ‚Ð¾Ñ€Ð¸ÑŽ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸ Ð±ÐµÐ· ÑÐµÑÑÐ¸Ð¸")
            return

        # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð² Ð¸ÑÑ‚Ð¾Ñ€Ð¸ÑŽ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸
        self.db.add_print_history(
            order_id=order_id,
            user_id=session.user_id,
            username=session.username,
            label_language=label_language,
            boxes_count=boxes_count
        )

        logger.info(f"Ð˜ÑÑ‚Ð¾Ñ€Ð¸Ñ Ð¿ÐµÑ‡Ð°Ñ‚Ð¸: {session.username} Ð½Ð°Ð¿ÐµÑ‡Ð°Ñ‚Ð°Ð» {order_id} ({label_language}, {boxes_count} ÐºÐ¾Ñ€Ð¾Ð±Ð¾Ðº)")

    async def handle_get_conditional_articles(self, websocket):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ñ… Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð²"""
        articles = self.db.get_conditional_articles()

        await websocket.send(json.dumps({
            'type': 'conditional_articles',
            'articles': articles
        }))

    async def handle_add_conditional_article(self, websocket, data):
        """Ð”Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»"""
        article_number = data.get('article_number')
        description = data.get('description', '')

        success = self.db.add_conditional_article(article_number, description)

        if success:
            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð½Ñ‹Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº Ð²ÑÐµÐ¼
            articles = self.db.get_conditional_articles()
            await self.sessions.broadcast_to_all({
                'type': 'conditional_articles',
                'articles': articles
            })
            logger.info(f"Ð”Ð¾Ð±Ð°Ð²Ð»ÐµÐ½ ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»: {article_number}")
        else:
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'ÐÑ€Ñ‚Ð¸ÐºÑƒÐ» {article_number} ÑƒÐ¶Ðµ ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÐµÑ‚'
            }))

    async def handle_remove_conditional_article(self, websocket, data):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»"""
        article_id = data.get('article_id')

        success = self.db.remove_conditional_article(article_id)

        if success:
            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð½Ñ‹Ð¹ ÑÐ¿Ð¸ÑÐ¾Ðº Ð²ÑÐµÐ¼
            articles = self.db.get_conditional_articles()
            await self.sessions.broadcast_to_all({
                'type': 'conditional_articles',
                'articles': articles
            })
            logger.info(f"Ð£Ð´Ð°Ð»ÐµÐ½ ÑƒÑÐ»Ð¾Ð²Ð½Ñ‹Ð¹ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ» ID: {article_id}")

    async def handle_save_picking_progress(self, ws, data):
        """
        Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ðµ ÑÐ±Ð¾Ñ€ÐºÐ¸ (Ð±ÐµÐ· Ð°Ð²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¾Ð³Ð¾ Ð·Ð°Ð¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ Ñ„Ð°ÐºÑ‚Ð° Ð¿Ñ€Ð¾Ð¸Ð·Ð²Ð¾Ð´ÑÑ‚Ð²Ð°)
        """
        oid = data.get('order_id')
        progress = data.get('progress', [])

        # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ ÑÑ‚Ð°Ñ‚ÑƒÑÑ‹ ÑÐ±Ð¾Ñ€ÐºÐ¸
        with self.db.get_connection() as conn:
            for item in progress:
                art_raw = str(item.get('artikel_nr') or '').strip()
                art_norm = art_raw.zfill(5) if art_raw.isdigit() else art_raw
                picked_qty = float(item.get('picked_qty', 0))
                checked = item.get('checked', False)

                # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ ÑÑ‚Ð°Ñ‚ÑƒÑ ÑÐ±Ð¾Ñ€ÐºÐ¸
                conn.execute("""
                    UPDATE order_picking
                    SET picked_qty=?, checked=?, updated_at=?
                    WHERE order_id=? AND (artikel_nr=? OR artikel_nr=?)
                """, (picked_qty, 1 if checked else 0, datetime.now().isoformat(), oid, art_raw, art_norm))

            conn.commit()

        # Ð Ð°ÑÑÑ‹Ð»Ð°ÐµÐ¼ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼
        updated_order = self.db.get_order(oid)
        assignment = self.db.get_order_assignment(oid)  # Ð’ÐÐ–ÐÐž: Ð’ÐºÐ»ÑŽÑ‡Ð°ÐµÐ¼ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð¾ ÑÐ±Ð¾Ñ€Ñ‰Ð¸ÐºÐµ!
        await self.sessions.broadcast_to_all({
            'type': 'picking_progress_update',
            'order_id': oid,
            'progress': self.db.get_picking_progress(oid),
            'boxes_count': updated_order.get('boxes_count', 0),
            'printed': updated_order.get('printed', False),
            'assignment': assignment  # Ð”Ð»Ñ Ð¾Ñ‚Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½Ð¸Ñ Ð¶ÐµÐ»Ñ‚Ð¾Ð³Ð¾ Ñ†Ð²ÐµÑ‚Ð° "Ð² Ñ€Ð°Ð±Ð¾Ñ‚Ðµ"
        })

    def _recalculate_production_fact(self, date_str):
        """
        Ð£ÐœÐÐÐ¯ Ð¡Ð˜ÐÐ¥Ð ÐžÐÐ˜Ð—ÐÐ¦Ð˜Ð¯ Ð¤ÐÐšÐ¢Ð v2:
        Ð‘ÐµÑ€ÐµÑ‚ Ð´Ð°Ð½Ð½Ñ‹Ðµ ÑÐ¾ ÑÐºÐ»Ð°Ð´Ð°. Ð•ÑÐ»Ð¸ Ñ€ÑƒÑ‡Ð½Ð¾Ð¹ Ñ„Ð°ÐºÑ‚ Ð±Ð¾Ð»ÑŒÑˆÐµ (Ð½Ð°Ð¿ÐµÐºÐ»Ð¸ Ð²Ð¿Ñ€Ð¾Ðº) â€” Ð¾ÑÑ‚Ð°Ð²Ð»ÑÐµÑ‚ Ñ€ÑƒÑ‡Ð½Ð¾Ð¹.
        Ð•ÑÐ»Ð¸ ÑÐºÐ»Ð°Ð´ ÑÐ¾Ð±Ñ€Ð°Ð» Ð±Ð¾Ð»ÑŒÑˆÐµ, Ñ‡ÐµÐ¼ Ð±Ñ‹Ð»Ð¾ Ð·Ð°Ð¿Ð¸ÑÐ°Ð½Ð¾ â€” Ð¾Ð±Ð½Ð¾Ð²Ð»ÑÐµÑ‚ Ð¿Ð¾ ÑÐºÐ»Ð°Ð´Ñƒ.
        Ð¤Ð°ÐºÑ‚ = MAX(Ð£Ð¶Ðµ_Ð’Ð²ÐµÐ´ÐµÐ½Ð¾_Ð ÑƒÐºÐ°Ð¼Ð¸, Ð¡Ð¾Ð±Ñ€Ð°Ð½Ð¾_Ð¡ÐºÐ»Ð°Ð´Ð¾Ð¼)
        """
        try:
            with self.db.get_connection() as conn:
                # 1. Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ Ð²Ñ€ÐµÐ¼ÐµÐ½Ð½ÑƒÑŽ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ ÑÐ¾ ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ¾Ð¹ ÑÐ¾ ÑÐºÐ»Ð°Ð´Ð°
                conn.execute("DROP TABLE IF EXISTS temp_picking_stats")
                conn.execute("""
                    CREATE TEMP TABLE temp_picking_stats AS
                    SELECT
                        op.artikel_nr,
                        SUM(op.picked_qty) as picked_total
                    FROM order_picking op
                    JOIN orders o ON op.order_id = o.order_id
                    WHERE o.production_date = ? AND op.checked = 1
                    GROUP BY op.artikel_nr
                """, (date_str,))

                # 2. Ð’ÑÑ‚Ð°Ð²Ð»ÑÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ðµ Ð·Ð°Ð¿Ð¸ÑÐ¸, ÐºÐ¾Ñ‚Ð¾Ñ€Ñ‹Ñ… Ð½ÐµÑ‚ Ð² production_facts
                conn.execute("""
                    INSERT INTO production_facts (date, article_nr, fact_qty)
                    SELECT ?, artikel_nr, picked_total
                    FROM temp_picking_stats
                    WHERE artikel_nr NOT IN (SELECT article_nr FROM production_facts WHERE date = ?)
                """, (date_str, date_str))

                # 3. ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÑŽÑ‰Ð¸Ðµ, Ð¢ÐžÐ›Ð¬ÐšÐž ÐµÑÐ»Ð¸ ÑÐºÐ»Ð°Ð´ ÑÐ¾Ð±Ñ€Ð°Ð» Ð±Ð¾Ð»ÑŒÑˆÐµ
                conn.execute("""
                    UPDATE production_facts
                    SET fact_qty = (SELECT picked_total FROM temp_picking_stats WHERE temp_picking_stats.artikel_nr = production_facts.article_nr)
                    WHERE date = ?
                    AND article_nr IN (SELECT artikel_nr FROM temp_picking_stats)
                    AND fact_qty < (SELECT picked_total FROM temp_picking_stats WHERE temp_picking_stats.artikel_nr = production_facts.article_nr)
                """, (date_str,))

                conn.execute("DROP TABLE IF EXISTS temp_picking_stats")
                conn.commit()
                logger.info(f"ðŸ”„ Auto-Fact updated for {date_str} (smart sync)")
        except Exception as e:
            logger.error(f"Fact recalc error: {e}")
    
    async def handle_assign_order(self, websocket, data):
        """ÐÐ°Ð·Ð½Ð°Ñ‡Ð¸Ñ‚ÑŒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ Ð½Ð° Ð·Ð°ÐºÐ°Ð·"""
        session = self.sessions.get_session(websocket)
        if not session:
            return

        order_id = data.get('order_id')
        force = data.get('force', False)  # ÐŸÑ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð¾Ðµ Ð¿ÐµÑ€ÐµÐ½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ðµ (Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð°Ð´Ð¼Ð¸Ð½)

        # Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð°Ð´Ð¼Ð¸Ð½ Ð¼Ð¾Ð¶ÐµÑ‚ Ð¿Ñ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð¾ Ð¿ÐµÑ€ÐµÐ½Ð°Ð·Ð½Ð°Ñ‡Ð¸Ñ‚ÑŒ
        if force and session.role != 'admin':
            force = False

        # ÐÐ°Ð·Ð½Ð°Ñ‡Ð°ÐµÐ¼ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»Ñ Ð½Ð° Ð·Ð°ÐºÐ°Ð·
        result = self.db.assign_user_to_order(order_id, session.user_id, session.username, force=force)

        if result['success']:
            logger.info(f"ÐŸÐ¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŒ {session.username} Ð½Ð°Ñ‡Ð°Ð» Ñ€Ð°Ð±Ð¾Ñ‚Ñƒ Ñ Ð·Ð°ÐºÐ°Ð·Ð¾Ð¼ {order_id}")

            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð¸Ð½Ñ„Ð¾Ñ€Ð¼Ð°Ñ†Ð¸ÑŽ Ð¾ Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ð¸
            assignment = self.db.get_order_assignment(order_id)

            # Ð Ð°ÑÑÑ‹Ð»Ð°ÐµÐ¼ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ Ð²ÑÐµÐ¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼
            await self.sessions.broadcast_to_all({
                'type': 'order_assignment_update',
                'order_id': order_id,
                'assignment': assignment
            })
        else:
            # Ð—Ð°ÐºÐ°Ð· ÑƒÐ¶Ðµ Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½ Ð´Ñ€ÑƒÐ³Ð¾Ð¼Ñƒ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŽ
            await websocket.send(json.dumps({
                'type': 'assignment_failed',
                'order_id': order_id,
                'message': result['message'],
                'assigned_to': result['assigned_to']
            }))

    async def handle_get_picking_statistics(self, websocket, data):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÑƒ ÑÐ±Ð¾Ñ€ÐºÐ¸ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²"""
        session = self.sessions.get_session(websocket)
        if not session:
            return

        # Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð¾Ð¿ÐµÑ€Ð°Ñ‚Ð¾Ñ€ Ð¸ Ð°Ð´Ð¼Ð¸Ð½ Ð¼Ð¾Ð³ÑƒÑ‚ Ð¿Ñ€Ð¾ÑÐ¼Ð°Ñ‚Ñ€Ð¸Ð²Ð°Ñ‚ÑŒ ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÑƒ
        if session.role not in ['operator', 'admin']:
            await websocket.send(json.dumps({
                'type': 'error',
                'message': 'ÐÐµÐ´Ð¾ÑÑ‚Ð°Ñ‚Ð¾Ñ‡Ð½Ð¾ Ð¿Ñ€Ð°Ð² Ð´Ð»Ñ Ð¿Ñ€Ð¾ÑÐ¼Ð¾Ñ‚Ñ€Ð° ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ¸'
            }))
            return

        start_date = data.get('start_date')
        end_date = data.get('end_date')

        # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÑƒ Ð¸Ð· Ð±Ð°Ð·Ñ‹
        statistics = self.db.get_picking_statistics(start_date, end_date)

        # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚
        await websocket.send(json.dumps({
            'type': 'picking_statistics',
            'statistics': statistics
        }))

        logger.info(f"Ð¡Ñ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ° ÑÐ±Ð¾Ñ€ÐºÐ¸ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÐµÐ½Ð° Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÑŽ {session.username} ({start_date} - {end_date})")

    # ============================================
    # ÐžÐ‘Ð ÐÐ‘ÐžÐ¢Ð§Ð˜ÐšÐ˜ Ð˜ÐÐ’Ð•ÐÐ¢ÐÐ Ð˜Ð—ÐÐ¦Ð˜Ð˜ (ÐžÐ¢Ð§Ð•Ð¢Ð« Ð¡ÐšÐ›ÐÐ”Ð)
    # ============================================
    async def handle_get_inventory_articles(self, websocket):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ ÑÐ¿Ð¸ÑÐ¾Ðº Ð²ÑÐµÑ… Ð°ÐºÑ‚Ð¸Ð²Ð½Ñ‹Ñ… Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Ð´Ð»Ñ Ð¸Ð½Ð²ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð·Ð°Ñ†Ð¸Ð¸ (Ð¡ ÐÐ£Ð›Ð¯ÐœÐ˜)"""
        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT article_nr, name
                FROM recipes
                WHERE active = 1
                ORDER BY article_nr
            """)
        
            # --- Ð˜Ð¡ÐŸÐ ÐÐ’Ð›Ð•ÐÐ˜Ð•: ÐŸÐ Ð˜ÐÐ£Ð”Ð˜Ð¢Ð•Ð›Ð¬ÐÐž 5 Ð—ÐÐÐšÐžÐ’ ---
            articles = []
            for row in cursor.fetchall():
                raw_art = str(row['article_nr']).strip()
                art_clean = raw_art.zfill(5) if raw_art.isdigit() else raw_art
                articles.append({'article_nr': art_clean, 'name': row['name'] or ''})
            # -------------------------------------------

            await websocket.send(json.dumps({
                'type': 'inventory_articles',
                'articles': articles
            }))

        except Exception as e:
            logger.error(f"Error getting inventory articles: {e}")
        finally:
            conn.close()

    async def handle_save_daily_stock_report(self, websocket, data):
        """
        ÐÐ²Ñ‚Ð¾ÑÐ¾Ñ…Ñ€Ð°Ð½ÐµÐ½Ð¸Ðµ Ð¾Ñ‚Ñ‡ÐµÑ‚Ð° (Ð¿Ð¾ Ð¾Ð´Ð½Ð¾Ð¹ Ð¿Ð¾Ð·Ð¸Ñ†Ð¸Ð¸ Ð¸Ð»Ð¸ Ð¼Ð°ÑÑÐ¾Ð²Ð¾).
        ÐŸÐ¸ÑˆÐµÑ‚, ÐšÐ¢Ðž ÑÐ¾Ñ…Ñ€Ð°Ð½Ð¸Ð», Ð¸ ÑÑ€Ð°Ð·Ñƒ Ð¾Ð±Ð½Ð¾Ð²Ð»ÑÐµÑ‚ Ð¿Ð»Ð°Ð½.
        """
        session = self.sessions.get_session(websocket)
        username = session.username if session else "Unknown"
    
        date = data.get('date')
        report_data = data.get('report_data', [])
        past_date_password = data.get('past_date_password', '')
        op_ids = []

        # Прошлые даты: редактирование только с паролем.
        try:
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
            today = datetime.now().date()
            if target_date < today and past_date_password != "admin":
                logger.warning(
                    f"Blocked past-date inventory save: user={username}, date={date}, items={len(report_data)}"
                )
                await websocket.send(json.dumps({
                    'type': 'error',
                    'message': 'Редактирование прошлых дат запрещено без пароля'
                }))
                return
        except Exception:
            # Если дата невалидная, отработает обычный обработчик/ошибка ниже.
            pass

        conn = self.db.get_connection()
        cursor = conn.cursor()
    
        try:
            for item in report_data:
                # 1. ÐÐ¾Ñ€Ð¼Ð°Ð»Ð¸Ð·Ð°Ñ†Ð¸Ñ (5502 -> 05502)
                raw_art = str(item.get('article_nr', '')).strip()
                article_nr = raw_art.zfill(5) if raw_art.isdigit() else raw_art
                quantity = float(item.get('quantity', 0))
                op_id = str(item.get('op_id', '')).strip()
                if op_id:
                    op_ids.append(op_id)

                # 2. UPSERT (Ð’ÑÑ‚Ð°Ð²ÐºÐ° Ð¸Ð»Ð¸ ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¸Ðµ)
                cursor.execute('''
                    INSERT INTO daily_stock_reports (date, article_nr, quantity, last_editor, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(date, article_nr) DO UPDATE SET
                    quantity = excluded.quantity,
                    last_editor = excluded.last_editor,
                    updated_at = excluded.updated_at
                ''', (date, article_nr, quantity, username, datetime.now().isoformat()))

            conn.commit()
            logger.info(f"ðŸ’¾ Ð˜Ð½Ð²ÐµÐ½Ñ‚Ð°Ñ€Ð¸Ð·Ð°Ñ†Ð¸Ñ {date}: Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾ {len(report_data)} Ð¿Ð¾Ð·. (User: {username})")

        
            # 3. Ð£Ð’Ð•Ð”ÐžÐœÐ›Ð•ÐÐ˜Ð• (Ð’Ð¼ÐµÑÑ‚Ð¾ Ð¿Ñ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð¾Ð³Ð¾ Ñ€Ð°ÑÑ‡ÐµÑ‚Ð°)
            await self.sessions.broadcast_to_all({
                'type': 'stock_updated',
                'date': date
            })

            # Подтверждение для локальной очереди клиента (без модальных окон на UI).
            await websocket.send(json.dumps({
                'type': 'inventory_ops_saved',
                'date': date,
                'count': len(report_data),
                'op_ids': op_ids[:1000]
            }))

        except Exception as e:
            logger.error(f"Save stock error: {e}")
        finally:
            conn.close()

    async def handle_get_daily_stock_report(self, websocket, data):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð¾Ñ‚Ñ‡ÐµÑ‚ ÑÐºÐ»Ð°Ð´Ð° Ð·Ð° Ð´Ð°Ñ‚Ñƒ + Ð·Ð° Ð¿Ñ€ÐµÐ´Ñ‹Ð´ÑƒÑ‰Ð¸Ð¹ Ð´ÐµÐ½ÑŒ"""
        date = data.get('date')
    
        # 1. Ð¢ÐµÐºÑƒÑ‰Ð¸Ð¹ Ð¾Ñ‚Ñ‡ÐµÑ‚
        report = self.db.get_daily_stock_report(date)
    
        # 2. ÐŸÑ€Ð¾ÑˆÐ»Ñ‹Ð¹ Ð¾Ñ‚Ñ‡ÐµÑ‚ (Ð´Ð»Ñ ÑÑ€Ð°Ð²Ð½ÐµÐ½Ð¸Ñ)
        try:
            current_dt = datetime.strptime(date, '%Y-%m-%d')
            prev_dt = current_dt - timedelta(days=1)
            prev_date = prev_dt.strftime('%Y-%m-%d')
        
            raw_prev_report = self.db.get_daily_stock_report(prev_date)
        
            # ÐŸÑ€ÐµÐ²Ñ€Ð°Ñ‰Ð°ÐµÐ¼ Ð² ÑÐ»Ð¾Ð²Ð°Ñ€ÑŒ { '05502': 100 }
            prev_map = {}
            for item in raw_prev_report:
                raw_art = str(item.get('article_nr', '')).strip()
                key = raw_art.zfill(5) if raw_art.isdigit() else raw_art
                prev_map[key] = item.get('quantity', 0)
            
        except Exception as e:
            logger.error(f"Error getting prev report: {e}")
            prev_map = {}

        await websocket.send(json.dumps({
            'type': 'daily_stock_report',
            'date': date,
            'report': report,
            'prev_data': prev_map
        }))

        logger.info(f"Daily stock report sent for {date}: {len(report)} items")

    async def handle_get_all_logistics(self, websocket):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ñ‹ Ð¸ Ð½Ð°Ð·Ð½Ð°Ñ‡ÐµÐ½Ð¸Ñ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²"""
        session = self.sessions.get_session(websocket)
        if not session:
            return

        # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ñ‹ Ð¸ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² Ð¸Ð· Ð±Ð°Ð·Ñ‹
        logistics_data = self.db.get_all_logistics()

        # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚
        await websocket.send(json.dumps({
            'type': 'logistics_data',
            'routes': logistics_data['routes'],
            'clients': logistics_data['clients']
        }))

        logger.info(f"Logistics data sent to {session.username} ({len(logistics_data['routes'])} routes, {len(logistics_data['clients'])} clients)")

    async def handle_save_logistics_rule(self, websocket, data):
        """ÐÐ°Ð·Ð½Ð°Ñ‡Ð¸Ñ‚ÑŒ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ñƒ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚"""
        session = self.sessions.get_session(websocket)
        if not session:
            return

        client_id = data.get('client_id')
        client_name = data.get('client_name', '')
        route_id = data.get('route_id')

        # Ð’Ð°Ð»Ð¸Ð´Ð°Ñ†Ð¸Ñ
        if not client_id or not route_id:
            await websocket.send(json.dumps({
                'type': 'error',
                'message': 'Client ID and Route ID are required'
            }))
            return

        # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð² Ð±Ð°Ð·Ñƒ
        success = self.db.save_client_route(client_id, client_name, route_id)

        if success:
            logger.info(f"Client route saved: {client_id} - {client_name} â†’ {route_id}")

            # Синхронизируем маршрут во всех активных заказах клиента
            updated_order_ids = self.db.update_orders_route_by_client(client_id, route_id)
            if updated_order_ids:
                route_name = route_id
                try:
                    with self.db.safe_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT route_name FROM logistics_routes WHERE route_id = ?", (route_id,))
                        row = cursor.fetchone()
                        route_name = row['route_name'] if row else route_id
                except Exception:
                    pass

                for order_id in updated_order_ids:
                    await self.sessions.broadcast_to_all({
                        'type': 'order_update',
                        'order_id': order_id,
                        'update': {
                            'route_id': route_id,
                            'route_name': route_name
                        }
                    })

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð²ÑÐµÐ¼ Ð°Ð´Ð¼Ð¸Ð½Ð°Ð¼
            all_logistics = self.db.get_all_logistics()
            await self.sessions.broadcast_to_role('admin', {
                'type': 'logistics_data',
                'routes': all_logistics['routes'],
                'clients': all_logistics['clients']
            })
        else:
            await websocket.send(json.dumps({
                'type': 'error',
                'message': 'Failed to save logistics rule'
            }))

    async def handle_update_logistics_route(self, websocket, data):
        """ÐžÐ±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð¿Ð°Ñ€Ð°Ð¼ÐµÑ‚Ñ€Ñ‹ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚Ð°"""
        session = self.sessions.get_session(websocket)
        if not session:
            return

        route_id = data.get('route_id')
        delivery_days = data.get('delivery_days', [])
        lead_time = data.get('lead_time', 1)

        # Ð’Ð°Ð»Ð¸Ð´Ð°Ñ†Ð¸Ñ
        if not route_id:
            await websocket.send(json.dumps({
                'type': 'error',
                'message': 'Route ID is required'
            }))
            return

        # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ Ð² Ð±Ð°Ð·Ðµ
        success = self.db.update_logistics_route(route_id, delivery_days, lead_time)

        if success:
            logger.info(f"Logistics route updated: {route_id} - days: {delivery_days}, lead_time: {lead_time}")

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ð¾Ð±Ð½Ð¾Ð²Ð»ÐµÐ½Ð½Ñ‹Ðµ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð²ÑÐµÐ¼ Ð°Ð´Ð¼Ð¸Ð½Ð°Ð¼
            all_logistics = self.db.get_all_logistics()
            await self.sessions.broadcast_to_role('admin', {
                'type': 'logistics_data',
                'routes': all_logistics['routes'],
                'clients': all_logistics['clients']
            })
        else:
            await websocket.send(json.dumps({
                'type': 'error',
                'message': 'Failed to update logistics route'
            }))

    # ============================================
    # Ð¤ÐžÐÐžÐ’Ð«Ð• Ð—ÐÐ”ÐÐ§Ð˜
    # ============================================
    async def woocommerce_sync_loop(self):
        """Ð¡Ð¸Ð½Ñ…Ñ€Ð¾Ð½Ð¸Ð·Ð°Ñ†Ð¸Ñ Ñ WooCommerce"""
        while True:
            try:
                orders = await self._run_sync(self.woocommerce.fetch_new_orders)

                for order in orders:
                    order_id = str(order.get('id'))

                    # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼, ÐµÑÑ‚ÑŒ Ð»Ð¸ ÑƒÐ¶Ðµ ÑÑ‚Ð¾Ñ‚ Ð·Ð°ÐºÐ°Ð·
                    existing_orders = await self._run_sync(self.db.get_all_orders)
                    if not any(o['order_id'] == order_id for o in existing_orders):
                        # ÐŸÑ€ÐµÐ¾Ð±Ñ€Ð°Ð·ÑƒÐµÐ¼ Ð·Ð°ÐºÐ°Ð· WooCommerce Ð² Ð½Ð°Ñˆ Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚
                        order_data = self.convert_woocommerce_order(order)

                        # ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ ÑÐºÐ»Ð°Ð´ (Ð¼Ð¾Ð¶Ð½Ð¾ Ð´Ð¾Ð±Ð°Ð²Ð¸Ñ‚ÑŒ Ð»Ð¾Ð³Ð¸ÐºÑƒ Ñ€Ð°ÑÐ¿Ñ€ÐµÐ´ÐµÐ»ÐµÐ½Ð¸Ñ)
                        warehouse_id = 'WAREHOUSE_1'

                        # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð² Ð‘Ð”
                        await self._run_sync(self.db.create_order, order_id, order_data, warehouse_id)

                        # ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñ‹ Ð² Ð±Ð°Ð·Ñƒ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² Ð¸ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸
                        self.auto_add_new_articles_from_order(order_data.get('artikel', []))

                        # Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ Ð²ÑÐµÑ… ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
                        await self.sessions.broadcast_to_all({
                            'type': 'new_order',
                            'order_id': order_id,
                            'order_data': order_data
                        })

                        logger.info(f"ÐÐ¾Ð²Ñ‹Ð¹ Ð·Ð°ÐºÐ°Ð· Ð¸Ð· WooCommerce: {order_id}")

            except Exception as e:
                logger.error(f"ÐžÑˆÐ¸Ð±ÐºÐ° ÑÐ¸Ð½Ñ…Ñ€Ð¾Ð½Ð¸Ð·Ð°Ñ†Ð¸Ð¸ WooCommerce: {e}")

            await asyncio.sleep(60)  # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ ÐºÐ°Ð¶Ð´ÑƒÑŽ Ð¼Ð¸Ð½ÑƒÑ‚Ñƒ

    def convert_woocommerce_order(self, woo_order: dict) -> dict:
        """ÐšÐ¾Ð½Ð²ÐµÑ€Ñ‚Ð¸Ñ€Ð¾Ð²Ð°Ñ‚ÑŒ Ð·Ð°ÐºÐ°Ð· WooCommerce Ð² Ð½Ð°Ñˆ Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚"""
        billing = woo_order.get('billing', {})
        shipping = woo_order.get('shipping', {})

        kunde = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()

        address_parts = [
            shipping.get('address_1', ''),
            shipping.get('address_2', ''),
            shipping.get('postcode', ''),
            shipping.get('city', ''),
            shipping.get('country', '')
        ]
        address = ', '.join(filter(None, address_parts))

        artikel = []
        for item in woo_order.get('line_items', []):
            artikel.append({
                'nummer': item.get('sku', item.get('id')),
                'name': item.get('name'),
                'menge': item.get('quantity', 1)
            })

        created_at = datetime.now().isoformat()
        return {
            'order_id': str(woo_order.get('id')),
            'date': woo_order.get('date_created', datetime.now().isoformat())[:10],
            'created_at': created_at,  # Ð”Ð°Ñ‚Ð° Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸
            'kunde': kunde,
            'address': address,
            'artikel': artikel,
            'lieferschein': str(woo_order.get('id')),
            'total_boxes': max(1, len(artikel) // 10 + 1),
            'status': 'pending',
            'printed': False
        }

    def on_new_lieferschein(self, filepath: Path) -> bool:
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ð½Ð¾Ð²Ð¾Ð³Ð¾ Lieferschein PDF Ñ„Ð°Ð¹Ð»Ð°"""
        try:
            logger.info(f"Processing Lieferschein PDF: {filepath.name}")

            # ÐŸÐ°Ñ€ÑÐ¸Ð¼ PDF Ñ„Ð°Ð¹Ð»
            parsed_data = self.pdf_parser.parse_lieferschein(filepath)

            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð½Ð¾Ð¼ÐµÑ€ Lieferschein
            lieferschein_nr = parsed_data.get('nummer', parsed_data.get('lieferschein_nummer', 'UNKNOWN'))

            # ÐŸÐ ÐžÐ’Ð•Ð Ð¯Ð•Ðœ: ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÐµÑ‚ Ð»Ð¸ ÑƒÐ¶Ðµ Ð·Ð°ÐºÐ°Ð· Ñ Ñ‚Ð°ÐºÐ¸Ð¼ Ð½Ð¾Ð¼ÐµÑ€Ð¾Ð¼ Lieferschein
            if self.db.order_exists_by_lieferschein(lieferschein_nr):
                logger.warning(f"âš ï¸  Lieferschein {lieferschein_nr} already exists in database! Skipping duplicate.")
                logger.warning(f"âš ï¸  File NOT deleted: {filepath.name}")

                # ÐÐ• ÑƒÐ´Ð°Ð»ÑÐµÐ¼ Ñ„Ð°Ð¹Ð» - Ð²Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÐ¼ False, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ñ„Ð°Ð¹Ð» Ð¾ÑÑ‚Ð°Ð»ÑÑ
                return False

            # ÐŸÑ€ÐµÐ¾Ð±Ñ€Ð°Ð·ÑƒÐµÐ¼ artikel Ð² Ð½ÑƒÐ¶Ð½Ñ‹Ð¹ Ñ„Ð¾Ñ€Ð¼Ð°Ñ‚ (Ñ€Ð°Ð±Ð¾Ñ‡Ð°Ñ Ð²ÐµÑ€ÑÐ¸Ñ Ð²Ð¾Ð·Ð²Ñ€Ð°Ñ‰Ð°ÐµÑ‚ 'nummer', 'menge', 'name')
            artikel_list = []
            for art in parsed_data['artikel']:
                artikel_list.append({
                    'nummer': art.get('nummer', art.get('artikelnr', '')),
                    'menge': art.get('menge', art.get('anzahl', 0)),
                    'beschreibung': art.get('name', art.get('bezeichnung', ''))
                })

            # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ Ð·Ð°ÐºÐ°Ð· Ñ ID = Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð½Ð¾Ð¼ÐµÑ€ Lieferschein (Ð‘Ð•Ð— timestamp!)
            order_id = f"LS-{lieferschein_nr}"
            # Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ Ñ‚ÐµÐºÑƒÑ‰ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ/Ð²Ñ€ÐµÐ¼Ñ Ð´Ð»Ñ ÑÐ¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²ÐºÐ¸ (Ð´Ð°Ñ‚Ð° Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸)
            created_at = datetime.now().isoformat()
            # ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ warehouse_id (Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ '1')
            warehouse_id = '1'

            order_data = {
                'lieferschein': lieferschein_nr,
                'date': parsed_data.get('datum', ''),  # Ð”Ð°Ñ‚Ð° Ð¸Ð· Lieferschein (Ð´Ð»Ñ Ð¾Ñ‚Ð¾Ð±Ñ€Ð°Ð¶ÐµÐ½Ð¸Ñ)
                'created_at': created_at,  # Ð”Ð°Ñ‚Ð° Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸ (Ð´Ð»Ñ ÑÐ¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²ÐºÐ¸)
                'kunde': parsed_data.get('kunde', 'Unknown'),
                'address': parsed_data.get('adresse', ''),
                'artikel': artikel_list,
                'kunden_nr': parsed_data.get('kunden_nr', ''),
                'total_boxes': max(1, len(artikel_list) // 10 + 1),
                'status': 'pending',
                'printed': False,
                'warehouse_id': warehouse_id  # Ð’ÐÐ–ÐÐž: Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ warehouse_id Ð² Ð´Ð°Ð½Ð½Ñ‹Ðµ!
            }
            self.db.create_order(order_id, order_data, warehouse_id)

            # ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñ‹ Ð² Ð±Ð°Ð·Ñƒ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² Ð¸ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸
            self.auto_add_new_articles_from_order(artikel_list)

            logger.info(f"âœ… Order created: {order_id} for Lieferschein {lieferschein_nr}")

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ ÑƒÐ²ÐµÐ´Ð¾Ð¼Ð»ÐµÐ½Ð¸Ðµ Ð²ÑÐµÐ¼ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð½Ñ‹Ð¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼
            # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ task Ð´Ð»Ñ broadcast (Ð½Ðµ Ð±Ð»Ð¾ÐºÐ¸Ñ€ÑƒÐµÐ¼ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÑƒ Ñ„Ð°Ð¹Ð»Ð°)
            try:
                logger.info(f"ðŸ“¡ Creating broadcast task for order {order_id}...")
                task = asyncio.create_task(self.broadcast_new_order(order_id, order_data))
                # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ callback Ð´Ð»Ñ Ð»Ð¾Ð³Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ñ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ð°
                task.add_done_callback(lambda t: self._log_broadcast_result(t, order_id))
                logger.info(f"âœ“ Broadcast task created for order {order_id}")
            except Exception as broadcast_error:
                logger.error(f"âŒ Failed to create broadcast task for order {order_id}: {broadcast_error}")
                import traceback
                traceback.print_exc()

            return True

        except Exception as e:
            logger.error(f"Error processing Lieferschein {filepath.name}: {e}")
            import traceback
            traceback.print_exc()
            self.db.log_error('lieferschein', 'processing_error', str(e))
            return False

    def on_new_csv_order(self, order_data: dict) -> bool:
        """
        ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ð½Ð¾Ð²Ð¾Ð³Ð¾ Ð·Ð°ÐºÐ°Ð·Ð° Ð¸Ð· CSV Ñ„Ð°Ð¹Ð»Ð° WISO ERP
        """
        try:
            # Ð¤Ð¾Ñ€Ð¼Ð¸Ñ€ÑƒÐµÐ¼ ID Ð·Ð°ÐºÐ°Ð·Ð° Ñ Ð¿Ñ€ÐµÑ„Ð¸ÐºÑÐ¾Ð¼ AB-, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð¾Ñ‚Ð»Ð¸Ñ‡Ð°Ñ‚ÑŒ Ð¾Ñ‚ Ð´Ñ€ÑƒÐ³Ð¸Ñ…
            raw_id = str(order_data.get('auftrag_nr'))
            order_id = f"AB-{raw_id}"
        
            kunde_name = order_data.get('kunde', 'Unknown')
            logger.info(f"Processing CSV order: {order_id} - {kunde_name}")

            # ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ warehouse_id (Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ '1' Ð¸Ð»Ð¸ Ð±ÐµÑ€ÐµÐ¼ Ð¸Ð· Ð»Ð¾Ð³Ð¸ÑÑ‚Ð¸ÐºÐ¸ ÐµÑÐ»Ð¸ Ð½ÑƒÐ¶Ð½Ð¾)
            warehouse_id = '1' 
            # ÐœÐ¾Ð¶Ð½Ð¾ ÑÐ´ÐµÐ»Ð°Ñ‚ÑŒ Ð»Ð¾Ð³Ð¸ÐºÑƒ: ÐµÑÐ»Ð¸ Ð¼Ð°Ñ€ÑˆÑ€ÑƒÑ‚ 'ost', Ñ‚Ð¾ warehouse_id='2' Ð¸ Ñ‚.Ð´.

            # Ð”Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ñ‚ÐµÑ…Ð½Ð¸Ñ‡ÐµÑÐºÐ¸Ðµ Ð¿Ð¾Ð»Ñ
            created_at = datetime.now().isoformat()
            order_data['created_at'] = created_at # Ð’Ð°Ð¶Ð½Ð¾ Ð´Ð»Ñ ÑÐ¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²ÐºÐ¸ Ð½Ð° ÑÐºÐ»Ð°Ð´Ðµ!
            order_data['status'] = 'pending'
        
            # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð² Ð±Ð°Ð·Ñƒ
            self.db.create_order(order_id, order_data, warehouse_id)

            # ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñ‹ Ð² Ð±Ð°Ð·Ñƒ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² Ð¸ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸
            self.auto_add_new_articles_from_order(order_data.get('artikel', []))

            # Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€ÑƒÐµÐ¼ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ ÐºÐ¾Ð¼Ð¿Ð»ÐµÐºÑ‚Ð°Ñ†Ð¸Ð¸ (Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð½Ð° ÑÐºÐ»Ð°Ð´Ðµ ÑÑ€Ð°Ð·Ñƒ Ð¼Ð¾Ð¶Ð½Ð¾ Ð±Ñ‹Ð»Ð¾ Ð¿Ð¸ÐºÐ°Ñ‚ÑŒ)
            self.db.init_order_picking(order_id, order_data['artikel'])

            # Ð¢Ñ€Ð°Ð½ÑÐ»Ð¸Ñ€ÑƒÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ð¹ Ð·Ð°ÐºÐ°Ð· Ð²ÑÐµÐ¼ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð½Ñ‹Ð¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼ ÐœÐ“ÐÐžÐ’Ð•ÐÐÐž
            asyncio.create_task(self.sessions.broadcast_to_all({
                'type': 'new_order',
                'order_id': order_id,
                'order_data': order_data
            }))

            logger.info(f"âœ… CSV order {order_id} created and broadcasted to Warehouse")
            return True

        except Exception as e:
            logger.error(f"Error processing CSV order: {e}", exc_info=True)
            return False

    def on_new_api_order(self, order_data: dict) -> bool:
        """
        ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ð½Ð¾Ð²Ð¾Ð³Ð¾ Ð·Ð°ÐºÐ°Ð·Ð° Ð¸Ð· Monolith API.
        ÐÐ½Ð°Ð»Ð¾Ð³Ð¸Ñ‡ÐµÐ½ on_new_csv_order, Ð½Ð¾ Ñ Ð¿Ñ€ÐµÑ„Ð¸ÐºÑÐ¾Ð¼ MO- Ð¸ Ñ„Ð»Ð°Ð³Ð¾Ð¼ is_api_new.
        """
        try:
            raw_id = str(order_data.get('auftrag_nr'))
            order_id = f"MO-{raw_id}"

            kunde_name = order_data.get('kunde', 'Unknown')
            logger.info(f"Processing API order: {order_id} - {kunde_name}")

            warehouse_id = '1'
            created_at = datetime.now().isoformat()
            order_data['created_at'] = created_at
            order_data['status'] = 'pending'

            # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ Ð² Ð±Ð°Ð·Ñƒ (Ð¾Ð´Ð½Ð¾ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ Ð´Ð»Ñ Ð²ÑÐµÑ… Ð¾Ð¿ÐµÑ€Ð°Ñ†Ð¸Ð¹)
            self.db.create_order(order_id, order_data, warehouse_id)

            # Ð£ÑÑ‚Ð°Ð½Ð°Ð²Ð»Ð¸Ð²Ð°ÐµÐ¼ Ñ„Ð»Ð°Ð³ is_api_new + Ð°Ð²Ñ‚Ð¾Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Ð² Ð¾Ð´Ð½Ð¾Ð¼ ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ð¸
            try:
                conn = self.db.get_connection()
                conn.execute("UPDATE orders SET is_api_new = 1 WHERE order_id = ?", (order_id,))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.warning(f"Failed to set is_api_new flag: {e}")

            # ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñ‹ Ð² Ð±Ð°Ð·Ñƒ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² Ð¸ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸
            self.auto_add_new_articles_from_order(order_data.get('artikel', []))

            # Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€ÑƒÐµÐ¼ Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñƒ ÐºÐ¾Ð¼Ð¿Ð»ÐµÐºÑ‚Ð°Ñ†Ð¸Ð¸
            self.db.init_order_picking(order_id, order_data['artikel'])

            # Ð¢Ñ€Ð°Ð½ÑÐ»Ð¸Ñ€ÑƒÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ð¹ Ð·Ð°ÐºÐ°Ð· Ð²ÑÐµÐ¼ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð½Ñ‹Ð¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼
            # Ð’ÐÐ–ÐÐž: ÑÑ‚Ð° Ñ„ÑƒÐ½ÐºÑ†Ð¸Ñ Ð²Ñ‹Ð·Ñ‹Ð²Ð°ÐµÑ‚ÑÑ Ð¸Ð· executor-Ñ‚Ñ€ÐµÐ´Ð°,
            # Ð¿Ð¾ÑÑ‚Ð¾Ð¼Ñƒ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ ÑÐ¾Ñ…Ñ€Ð°Ð½Ñ‘Ð½Ð½Ñ‹Ð¹ _event_loop + call_soon_threadsafe
            try:
                loop = self._event_loop
                loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    self.sessions.broadcast_to_all({
                        'type': 'new_order',
                        'order_id': order_id,
                        'order_data': order_data,
                        'is_api_new': True
                    })
                )
            except Exception as e:
                logger.warning(f"Failed to broadcast API order: {e}")

            logger.info(f"âœ… API order {order_id} created and broadcasted")
            return True

        except Exception as e:
            logger.error(f"Error processing API order: {e}", exc_info=True)
            return False

    # ============================================
    # MONOLITH API: ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚Ñ‡Ð¸ÐºÐ¸ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ð¹
    # ============================================

    async def handle_get_article_mappings(self, websocket):
        """ÐŸÐ¾Ð»ÑƒÑ‡Ð¸Ñ‚ÑŒ Ð²ÑÐµ Ð¼Ð°Ð¿Ð¿Ð¸Ð½Ð³Ð¸ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð²."""
        with self.db.safe_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM article_mapping ORDER BY monolith_article_nr")
            mappings = [dict(row) for row in cursor.fetchall()]
        await websocket.send(json.dumps({
            'type': 'article_mappings',
            'mappings': mappings
        }))

    async def handle_save_article_mapping(self, websocket, data):
        """Ð¡Ð¾Ð·Ð´Ð°Ñ‚ÑŒ Ð¸Ð»Ð¸ Ð¾Ð±Ð½Ð¾Ð²Ð¸Ñ‚ÑŒ Ð¼Ð°Ð¿Ð¿Ð¸Ð½Ð³ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð°."""
        m = data.get('mapping', {})
        with self.db.safe_connection() as conn:
            now = datetime.now().isoformat()
            conn.execute("""
                INSERT INTO article_mapping (monolith_article_nr, wiso_article_nr, monolith_name, unit_price, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(monolith_article_nr) DO UPDATE SET
                    wiso_article_nr=excluded.wiso_article_nr,
                    monolith_name=excluded.monolith_name,
                    unit_price=excluded.unit_price,
                    updated_at=excluded.updated_at
            """, (m.get('monolith_article_nr', ''), m.get('wiso_article_nr', ''),
                  m.get('monolith_name', ''), float(m.get('unit_price', 0.0)), now, now))
            conn.commit()
        await self.handle_get_article_mappings(websocket)

    async def handle_delete_article_mapping(self, websocket, data):
        """Ð£Ð´Ð°Ð»Ð¸Ñ‚ÑŒ Ð¼Ð°Ð¿Ð¿Ð¸Ð½Ð³ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð°."""
        monolith_nr = data.get('monolith_article_nr')
        if monolith_nr:
            with self.db.safe_connection() as conn:
                conn.execute("DELETE FROM article_mapping WHERE monolith_article_nr = ?", (monolith_nr,))
                conn.commit()
        await self.handle_get_article_mappings(websocket)

    async def handle_save_client_monolith_id(self, websocket, data):
        """ÐŸÑ€Ð¸Ð²ÑÐ·Ð°Ñ‚ÑŒ monolith_client_id Ðº ÐºÐ»Ð¸ÐµÐ½Ñ‚Ñƒ WISO."""
        client_id = data.get('client_id')
        monolith_id = data.get('monolith_client_id', '').strip()
        if client_id:
            with self.db.safe_connection() as conn:
                conn.execute(
                    "UPDATE client_routes SET monolith_client_id = ?, updated_at = ? WHERE client_id = ?",
                    (monolith_id, datetime.now().isoformat(), client_id)
                )
                conn.commit()
            await self.broadcast_logistics_update()

    async def handle_mark_api_order_seen(self, websocket, data):
        """Ð¡Ð½ÑÑ‚ÑŒ Ñ„Ð»Ð°Ð³ is_api_new Ð¿Ñ€Ð¸ Ð¾Ñ‚ÐºÑ€Ñ‹Ñ‚Ð¸Ð¸ Ð·Ð°ÐºÐ°Ð·Ð° Ð¾Ð¿ÐµÑ€Ð°Ñ‚Ð¾Ñ€Ð¾Ð¼."""
        order_id = data.get('order_id', '')
        if order_id.startswith('MO-'):
            with self.db.safe_connection() as conn:
                conn.execute("UPDATE orders SET is_api_new = 0 WHERE order_id = ?", (order_id,))
                conn.commit()
            # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ order_data JSON Ñ‚Ð¾Ð¶Ðµ
            self.db.update_order(order_id, {'is_api_new': False})
            # Ð£Ð²ÐµÐ´Ð¾Ð¼Ð»ÑÐµÐ¼ Ð²ÑÐµÑ… ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
            await self.sessions.broadcast_to_all({
                'type': 'order_update',
                'order_id': order_id,
                'update': {'is_api_new': False}
            })

    async def handle_force_api_scan(self, websocket):
        """ÐŸÑ€Ð¸Ð½ÑƒÐ´Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ð¾Ðµ ÑÐºÐ°Ð½Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ API (admin only)."""
        self.api_monitor.last_fetch_time = None  # Ð¡Ð±Ñ€Ð¾Ñ throttle
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, self.api_monitor.scan),
            timeout=60
        )
        await websocket.send(json.dumps({
            'type': 'api_scan_complete',
            'message': 'API scan completed'
        }))

    async def handle_auto_fill_prices(self, websocket):
        """ÐÐ²Ñ‚Ð¾-Ð·Ð°Ð¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ðµ Ñ†ÐµÐ½ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð² Ð¸Ð· Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ð¸ Ð·Ð°ÐºÐ°Ð·Ð¾Ð²."""
        count = self._auto_fill_prices_from_history()
        await websocket.send(json.dumps({
            'type': 'auto_fill_prices_result',
            'count': count,
            'message': f'ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾ {count} Ñ†ÐµÐ½ Ð¸Ð· Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ð¸'
        }))

    def _get_recipe_prices_cache(self) -> dict:
        """Ð—Ð°Ð³Ñ€ÑƒÐ¶Ð°ÐµÑ‚ {article_nr: unit_price} Ð¸Ð· Ñ‚Ð°Ð±Ð»Ð¸Ñ†Ñ‹ recipes."""
        prices = {}
        try:
            with self.db.safe_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT article_nr, unit_price FROM recipes WHERE unit_price > 0")
                for row in cursor.fetchall():
                    art = str(row['article_nr']).strip()
                    if art.isdigit():
                        art = art.zfill(5)
                    prices[art] = float(row['unit_price'])
        except Exception as e:
            logger.warning(f"Error loading recipe prices cache: {e}")
        return prices

    def _auto_fill_prices_from_history(self) -> int:
        """
        Ð Ð°ÑÑ‡Ñ‘Ñ‚ unit_price Ð¸Ð· Ð¸ÑÑ‚Ð¾Ñ€Ð¸Ð¸ WISO Ð·Ð°ÐºÐ°Ð·Ð¾Ð².
        Ð”Ð»Ñ Ð·Ð°ÐºÐ°Ð·Ð¾Ð² Ñ 1 Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð¾Ð¼: unit_price = total_value / quantity (Ñ‚Ð¾Ñ‡Ð½Ð¾).
        ÐœÐµÐ´Ð¸Ð°Ð½Ð° Ð´Ð»Ñ Ð½ÐµÑÐºÐ¾Ð»ÑŒÐºÐ¸Ñ… Ð½Ð°Ð±Ð»ÑŽÐ´ÐµÐ½Ð¸Ð¹ (Ñ„Ð¸Ð»ÑŒÑ‚Ñ€ÑƒÐµÑ‚ Ð²Ñ‹Ð±Ñ€Ð¾ÑÑ‹).
        """
        with self.db.safe_connection() as conn:
            cursor = conn.cursor()

            # Ð‘ÐµÑ€Ñ‘Ð¼ WISO Ð·Ð°ÐºÐ°Ð·Ñ‹ Ñ Ð¸Ð·Ð²ÐµÑÑ‚Ð½Ð¾Ð¹ ÑÑƒÐ¼Ð¼Ð¾Ð¹
            cursor.execute("""
                SELECT order_id, order_data, total_value
                FROM orders
                WHERE order_id LIKE 'AB-%' AND total_value > 0
            """)

            price_observations = {}  # {article_nr: [unit_prices]}

            for row in cursor.fetchall():
                try:
                    data = json.loads(row['order_data'])
                    artikel = data.get('artikel', [])
                    total = float(row['total_value'] or 0)

                    # Ð¢Ð¾Ð»ÑŒÐºÐ¾ Ð¾Ð´Ð½Ð¾Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»ÑŒÐ½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ñ‹ â€” Ñ‚Ð¾Ñ‡Ð½Ñ‹Ð¹ Ñ€Ð°ÑÑ‡Ñ‘Ñ‚ Ñ†ÐµÐ½Ñ‹
                    if len(artikel) == 1 and total > 0:
                        art = artikel[0]
                        qty = float(art.get('menge', 0))
                        art_nr = art.get('artikel_nr', art.get('nummer', ''))
                        if qty > 0 and art_nr:
                            unit_price = total / qty
                            price_observations.setdefault(art_nr, []).append(unit_price)
                except Exception:
                    continue

            # ÐœÐµÐ´Ð¸Ð°Ð½Ð° Ð´Ð»Ñ ÐºÐ°Ð¶Ð´Ð¾Ð³Ð¾ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ð°
            updated = 0
            for art_nr, prices in price_observations.items():
                if not prices:
                    continue
                prices.sort()
                median_price = prices[len(prices) // 2]

                # ÐžÐ±Ð½Ð¾Ð²Ð»ÑÐµÐ¼ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ ÐµÑÐ»Ð¸ Ñ‚ÐµÐºÑƒÑ‰Ð°Ñ Ñ†ÐµÐ½Ð° = 0
                cursor.execute(
                    "UPDATE recipes SET unit_price = ? WHERE article_nr = ? AND (unit_price IS NULL OR unit_price = 0)",
                    (round(median_price, 2), art_nr)
                )
                if cursor.rowcount > 0:
                    updated += 1

            conn.commit()
            logger.info(f"[AUTO_PRICES] ÐžÐ±Ð½Ð¾Ð²Ð»ÐµÐ½Ð¾ {updated} Ñ†ÐµÐ½ Ð¸Ð· {len(price_observations)} Ð½Ð°Ð±Ð»ÑŽÐ´ÐµÐ½Ð¸Ð¹")
            return updated

    def on_new_auftrag(self, filepath: Path) -> bool:
        """ÐžÐ±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ð½Ð¾Ð²Ð¾Ð³Ð¾ AuftragsbestÃ¤tigung PDF Ñ„Ð°Ð¹Ð»Ð°"""
        try:
            logger.info(f"Processing AuftragsbestÃ¤tigung PDF: {filepath.name}")

            # ÐŸÐ°Ñ€ÑÐ¸Ð¼ PDF Ñ„Ð°Ð¹Ð»
            parsed_data = self.auftrag_parser.parse_auftrag(filepath)

            if not parsed_data:
                logger.error(f"Failed to parse AuftragsbestÃ¤tigung: {filepath.name}")
                return False

            # ÐŸÐ¾Ð»ÑƒÑ‡Ð°ÐµÐ¼ Ð½Ð¾Ð¼ÐµÑ€ Ð·Ð°ÐºÐ°Ð·Ð°
            auftrag_nr = parsed_data.get('auftrag_nr')
            if not auftrag_nr:
                logger.error(f"No auftrag_nr found in {filepath.name}")
                return False

            # ÐŸÐ ÐžÐ’Ð•Ð Ð¯Ð•Ðœ: ÑÑƒÑ‰ÐµÑÑ‚Ð²ÑƒÐµÑ‚ Ð»Ð¸ ÑƒÐ¶Ðµ Ð·Ð°ÐºÐ°Ð· Ñ Ñ‚Ð°ÐºÐ¸Ð¼ Ð½Ð¾Ð¼ÐµÑ€Ð¾Ð¼
            order_id = f"AB-{auftrag_nr}"
            if self.db.order_exists(order_id):
                logger.warning(f"âš ï¸  AuftragsbestÃ¤tigung {auftrag_nr} already exists in database! Skipping duplicate.")
                logger.warning(f"âš ï¸  File NOT deleted: {filepath.name}")
                return False

            # Ð˜ÑÐ¿Ð¾Ð»ÑŒÐ·ÑƒÐµÐ¼ Ñ‚ÐµÐºÑƒÑ‰ÑƒÑŽ Ð´Ð°Ñ‚Ñƒ/Ð²Ñ€ÐµÐ¼Ñ Ð´Ð»Ñ ÑÐ¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²ÐºÐ¸ (Ð´Ð°Ñ‚Ð° Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸)
            created_at = datetime.now().isoformat()
            # ÐžÐ¿Ñ€ÐµÐ´ÐµÐ»ÑÐµÐ¼ warehouse_id (Ð¿Ð¾ ÑƒÐ¼Ð¾Ð»Ñ‡Ð°Ð½Ð¸ÑŽ '1')
            warehouse_id = '1'

            # ÐŸÐ¾Ð´Ð³Ð¾Ñ‚Ð°Ð²Ð»Ð¸Ð²Ð°ÐµÐ¼ Ð´Ð°Ð½Ð½Ñ‹Ðµ Ð·Ð°ÐºÐ°Ð·Ð°
            order_data = {
                'auftrag_nr': auftrag_nr,
                'kunden_nr': parsed_data.get('kunden_nr', ''),
                'datum': parsed_data.get('datum', ''),  # Ð”Ð°Ñ‚Ð° Ð¸Ð· Auftrag
                'created_at': created_at,  # Ð”Ð°Ñ‚Ð° Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ¸ (Ð´Ð»Ñ ÑÐ¾Ñ€Ñ‚Ð¸Ñ€Ð¾Ð²ÐºÐ¸)
                'kunde': parsed_data.get('kunde', 'Unknown'),
                'address': parsed_data.get('address', ''),
                'artikel': parsed_data.get('artikel', []),
                'is_auftrag': True,  # Ð¤Ð»Ð°Ð³ Ñ‡Ñ‚Ð¾ ÑÑ‚Ð¾ AuftragsbestÃ¤tigung
                'status': 'pending',
                'printed': False,
                'warehouse_id': warehouse_id
            }

            # Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ Ð·Ð°ÐºÐ°Ð· Ð² Ð‘Ð”
            self.db.create_order(order_id, order_data, warehouse_id)

            # ÐÐ²Ñ‚Ð¾Ð¼Ð°Ñ‚Ð¸Ñ‡ÐµÑÐºÐ¸ Ð´Ð¾Ð±Ð°Ð²Ð»ÑÐµÐ¼ Ð½Ð¾Ð²Ñ‹Ðµ Ð°Ñ€Ñ‚Ð¸ÐºÑƒÐ»Ñ‹ Ð² Ð±Ð°Ð·Ñƒ Ñ€ÐµÑ†ÐµÐ¿Ñ‚Ð¾Ð² Ð¸ Ð¾ÑÑ‚Ð°Ñ‚ÐºÐ¸
            self.auto_add_new_articles_from_order(order_data.get('artikel', []))

            # Ð˜Ð½Ð¸Ñ†Ð¸Ð°Ð»Ð¸Ð·Ð¸Ñ€ÑƒÐµÐ¼ Ð¿Ñ€Ð¾Ð³Ñ€ÐµÑÑ ÐºÐ¾Ð¼Ð¿Ð»ÐµÐºÑ‚Ð°Ñ†Ð¸Ð¸
            self.db.init_order_picking(order_id, order_data['artikel'])

            logger.info(f"âœ… Order created: {order_id} for AuftragsbestÃ¤tigung {auftrag_nr}")

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ ÑƒÐ²ÐµÐ´Ð¾Ð¼Ð»ÐµÐ½Ð¸Ðµ Ð²ÑÐµÐ¼ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð½Ñ‹Ð¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼
            try:
                logger.info(f"ðŸ“¡ Creating broadcast task for order {order_id}...")
                task = asyncio.create_task(self.broadcast_new_order(order_id, order_data))
                task.add_done_callback(lambda t: self._log_broadcast_result(t, order_id))
                logger.info(f"âœ“ Broadcast task created for order {order_id}")
            except Exception as broadcast_error:
                logger.error(f"âŒ Failed to create broadcast task for order {order_id}: {broadcast_error}")
                import traceback
                traceback.print_exc()

            return True

        except Exception as e:
            logger.error(f"Error processing AuftragsbestÃ¤tigung {filepath.name}: {e}")
            import traceback
            traceback.print_exc()
            self.db.log_error('auftrag', 'processing_error', str(e))
            return False

    def _log_broadcast_result(self, task, order_id: str):
        """Ð›Ð¾Ð³Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚Ð° broadcast task"""
        try:
            # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ Ñ€ÐµÐ·ÑƒÐ»ÑŒÑ‚Ð°Ñ‚ Ð²Ñ‹Ð¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ task
            exception = task.exception()
            if exception:
                logger.error(f"âŒ Broadcast task failed for order {order_id}: {exception}")
            else:
                logger.info(f"âœ“ Broadcast task completed successfully for order {order_id}")
        except Exception as e:
            logger.error(f"âŒ Error checking broadcast task result: {e}")

    async def broadcast_new_order(self, order_id: str, order_data: dict):
        """ÐžÑ‚Ð¿Ñ€Ð°Ð²ÐºÐ° ÑƒÐ²ÐµÐ´Ð¾Ð¼Ð»ÐµÐ½Ð¸Ñ Ð¾ Ð½Ð¾Ð²Ð¾Ð¼ Ð·Ð°ÐºÐ°Ð·Ðµ Ð²ÑÐµÐ¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼"""
        try:
            total_sessions = len(self.sessions.sessions)
            logger.info(f"ðŸ“¡ Broadcasting order {order_id} to {total_sessions} connected clients...")

            if total_sessions == 0:
                logger.warning(f"âš ï¸ No clients connected - cannot broadcast order {order_id}")
                return

            message = json.dumps({
                'type': 'new_order',
                'order_id': order_id,
                'order_data': order_data
            })

            # Ð¡Ñ‡ÐµÑ‚Ñ‡Ð¸ÐºÐ¸
            success_count = 0
            failed_count = 0
            sessions_to_remove = []

            # ÐžÑ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ Ð²ÑÐµÐ¼ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð½Ñ‹Ð¼ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð°Ð¼
            for session_id, session in list(self.sessions.sessions.items()):
                try:
                    await session.websocket.send(message)
                    success_count += 1
                    logger.info(f"  âœ“ Sent to {session.username} ({session.role})")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"  âŒ Failed to send to {session.username} ({session.role}): {e}")
                    # ÐŸÐ¾Ð¼ÐµÑ‡Ð°ÐµÐ¼ ÑÐµÑÑÐ¸ÑŽ Ð´Ð»Ñ ÑƒÐ´Ð°Ð»ÐµÐ½Ð¸Ñ, ÐµÑÐ»Ð¸ ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ðµ Ð·Ð°ÐºÑ€Ñ‹Ñ‚Ð¾
                    if "close frame" in str(e).lower() or "closed" in str(e).lower():
                        sessions_to_remove.append(session_id)

            # Ð£Ð´Ð°Ð»ÑÐµÐ¼ Ð·Ð°ÐºÑ€Ñ‹Ñ‚Ñ‹Ðµ ÑÐµÑÑÐ¸Ð¸
            for session_id in sessions_to_remove:
                try:
                    session = self.sessions.sessions.get(session_id)
                    if session:
                        logger.warning(f"Removing closed session: {session.username}")
                    del self.sessions.sessions[session_id]
                except KeyError:
                    pass

            # Ð˜Ñ‚Ð¾Ð³Ð¾Ð²Ð°Ñ ÑÑ‚Ð°Ñ‚Ð¸ÑÑ‚Ð¸ÐºÐ°
            logger.info(f"ðŸ“Š Broadcast statistics for order {order_id}:")
            logger.info(f"   Total: {total_sessions}, Success: {success_count}, Failed: {failed_count}, Removed: {len(sessions_to_remove)}")

        except Exception as e:
            logger.error(f"âŒ Critical error in broadcast_new_order: {e}")
            import traceback
            traceback.print_exc()

    # lieferschein_monitor_loop REMOVED â€” Lieferschein Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ñ‚ÐµÐ¿ÐµÑ€ÑŒ Ð² rechnung_monitor

    async def csv_monitor_loop(self):
        """Ð¦Ð¸ÐºÐ» Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³Ð° CSV Ñ„Ð°Ð¹Ð»Ð° WISO ERP"""
        logger.info("WISO CSV monitor loop started")
        loop = asyncio.get_event_loop()
        consecutive_errors = 0

        while True:
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, self.csv_monitor.scan),
                    timeout=30
                )
                consecutive_errors = 0
                await asyncio.sleep(5)
            except asyncio.TimeoutError:
                consecutive_errors += 1
                backoff = min(60, 10 * consecutive_errors)
                logger.warning(f"CSV monitor scan timed out (errors: {consecutive_errors})")
                await asyncio.sleep(backoff)
            except Exception as e:
                consecutive_errors += 1
                backoff = min(60, 10 * consecutive_errors)
                logger.error(f"Error in CSV monitor loop: {e}", exc_info=True)
                await asyncio.sleep(backoff)

    # DEPRECATED: Old PDF-based Auftrag monitor
    # async def auftrag_monitor_loop(self):
    #     """Ð¦Ð¸ÐºÐ» Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³Ð° Ð¿Ð°Ð¿ÐºÐ¸ AuftragsbestÃ¤tigung"""
    #     self.auftrag_monitor.start()
    #     logger.info("Auftrag monitor loop started")
    #
    #     while True:
    #         try:
    #             # Ð¡ÐºÐ°Ð½Ð¸Ñ€ÑƒÐµÐ¼ Ð¿Ð°Ð¿ÐºÑƒ ÐºÐ°Ð¶Ð´Ñ‹Ðµ 2 ÑÐµÐºÑƒÐ½Ð´Ñ‹
    #             self.auftrag_monitor.scan()
    #             await asyncio.sleep(2)
    #         except Exception as e:
    #             logger.error(f"Error in auftrag monitor loop: {e}")
    #             await asyncio.sleep(5)

    async def rechnung_monitor_loop(self):
        """Ð¦Ð¸ÐºÐ» Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³Ð° ÑÑ‡ÐµÑ‚Ð¾Ð² (Ð£ÐœÐÐÐ¯ ÐŸÐ Ð˜Ð’Ð¯Ð—ÐšÐ)"""
        self.rechnung_monitor.start()
        logger.info("Rechnung monitor loop started with SMART LINKING")
        loop = asyncio.get_event_loop()
        # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ ÑÑÑ‹Ð»ÐºÑƒ Ð½Ð° loop Ð´Ð»Ñ broadcast Ð¸Ð· executor-Ñ‚Ñ€ÐµÐ´Ð°
        self.rechnung_monitor._event_loop = loop
        _loop_count = 0
        consecutive_errors = 0

        while True:
            try:
                _loop_count += 1
                executor = getattr(self, '_monitor_executor', None)
                results = await asyncio.wait_for(
                    loop.run_in_executor(executor, self.rechnung_monitor.scan),
                    timeout=60
                )
                consecutive_errors = 0

                for result in results:
                    if not result.get('success'):
                        continue

                    rechnung_nr = result.get('rechnung_nr', 'unknown')
                    matched_order_ids = result.get('matched_orders', [])

                    # process_file() ÑƒÐ¶Ðµ Ð½Ð°ÑˆÑ‘Ð» Ð¸ Ð¾Ð±Ð½Ð¾Ð²Ð¸Ð» Ð·Ð°ÐºÐ°Ð·Ñ‹ â€” Ð¿Ñ€Ð¾ÑÑ‚Ð¾ Ð¾Ñ‚Ð¿Ñ€Ð°Ð²Ð»ÑÐµÐ¼ broadcast
                    if matched_order_ids:
                        invoice_file = result.get('output_file', '')
                        for order_id in matched_order_ids:
                            await self.sessions.broadcast_to_all({
                                'type': 'invoice_processed',
                                'order_id': order_id,
                                'rechnung_nr': rechnung_nr,
                                'invoice_file': invoice_file,
                                'update': {
                                    'invoice_status': f'âœ… {rechnung_nr}',
                                    'invoice_file': invoice_file
                                }
                            })
                        logger.info(f"Rechnung {rechnung_nr} -> Orders {matched_order_ids} (broadcast sent)")
                    else:
                        logger.warning(f"Rechnung {rechnung_nr} processed but no matching order found")

                await asyncio.sleep(10)
            except asyncio.TimeoutError:
                consecutive_errors += 1
                backoff = min(120, 15 * consecutive_errors)
                logger.warning(f"Rechnung monitor scan timed out (loop #{_loop_count}, errors: {consecutive_errors})")
                await asyncio.sleep(backoff)
            except Exception as e:
                consecutive_errors += 1
                backoff = min(120, 15 * consecutive_errors)
                logger.error(f"Error in rechnung monitor loop (#{_loop_count}): {e}")
                await asyncio.sleep(backoff)

    async def api_monitor_loop(self):
        """Ð¦Ð¸ÐºÐ» Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³Ð° Monolith API â€” ÐºÐ°Ð¶Ð´Ñ‹Ðµ 10 Ð¼Ð¸Ð½ÑƒÑ‚"""
        # Ð”Ð°Ñ‘Ð¼ ÑÐµÑ€Ð²ÐµÑ€Ñƒ Ð²Ñ€ÐµÐ¼Ñ Ð¿Ñ€Ð¸Ð½ÑÑ‚ÑŒ Ð¿ÐµÑ€Ð²Ñ‹Ðµ Ð¿Ð¾Ð´ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ñ
        await asyncio.sleep(10)

        loop = asyncio.get_event_loop()
        # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ ÑÑÑ‹Ð»ÐºÑƒ Ð½Ð° loop Ð´Ð»Ñ Ð¸ÑÐ¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ð½Ð¸Ñ Ð¸Ð· executor-Ñ‚Ñ€ÐµÐ´Ð¾Ð²
        self._event_loop = loop
        self.api_monitor._event_loop = loop
        self.rechnung_monitor._event_loop = loop
        executor = getattr(self, '_monitor_executor', None)
        logger.info("Performing initial API scan...")
        try:
            # Ð’ÐÐ–ÐÐž: HTTP-Ð·Ð°Ð¿Ñ€Ð¾Ñ Ð±Ð»Ð¾ÐºÐ¸Ñ€ÑƒÑŽÑ‰Ð¸Ð¹ â€” Ð·Ð°Ð¿ÑƒÑÐºÐ°ÐµÐ¼ Ð² Ð²Ñ‹Ð´ÐµÐ»ÐµÐ½Ð½Ð¾Ð¼ executor Ñ Ñ‚Ð°Ð¹Ð¼Ð°ÑƒÑ‚Ð¾Ð¼
            await asyncio.wait_for(
                loop.run_in_executor(executor, self.api_monitor.scan),
                timeout=60  # ÐœÐ°ÐºÑ 60 ÑÐµÐºÑƒÐ½Ð´ Ð½Ð° scan
            )
        except asyncio.TimeoutError:
            logger.error("Initial API scan timed out after 60s")
        except Exception as e:
            logger.error(f"Initial API scan failed: {e}")

        logger.info(f"Starting Monolith API monitor loop (every {self.api_monitor.poll_interval}s)")
        consecutive_errors = 0
        while True:
            try:
                await asyncio.sleep(60)
                # ÐŸÑ€Ð¾Ð¿ÑƒÑÐºÐ°ÐµÐ¼ ÐµÑÐ»Ð¸ refresh_with_api_scan ÑƒÐ¶Ðµ Ð·Ð°Ð¿ÑƒÑÑ‚Ð¸Ð» scan
                if self._api_scan_lock and self._api_scan_lock.locked():
                    logger.debug("API scan lock held by refresh, skipping periodic scan")
                    continue
                async with self._api_scan_lock:
                    await asyncio.wait_for(
                        loop.run_in_executor(executor, self.api_monitor.scan),
                        timeout=90
                    )
                consecutive_errors = 0
            except asyncio.TimeoutError:
                consecutive_errors += 1
                backoff = min(300, 30 * consecutive_errors)
                logger.error(f"API monitor scan timed out (errors: {consecutive_errors}, backoff: {backoff}s)")
                await asyncio.sleep(backoff)
            except Exception as e:
                consecutive_errors += 1
                backoff = min(300, 30 * consecutive_errors)
                logger.error(f"Error in API monitor loop: {e} (errors: {consecutive_errors})", exc_info=True)
                await asyncio.sleep(backoff)

    async def _db_keepalive_loop(self):
        """Ð¤Ð¾Ð½Ð¾Ð²Ð°Ñ Ð·Ð°Ð´Ð°Ñ‡Ð°: Ð¿Ð¸Ð½Ð³ Ð±Ð°Ð·Ñ‹ Ð´Ð°Ð½Ð½Ñ‹Ñ…, Ñ‡Ñ‚Ð¾Ð±Ñ‹ SMB-ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ðµ Ð½Ðµ Ð¾Ñ‚Ð²Ð°Ð»Ð¸Ð²Ð°Ð»Ð¾ÑÑŒ"""
        logger.info("Database keepalive loop started")
        while True:
            try:
                # Ð–Ð´ÐµÐ¼ 5 Ð¼Ð¸Ð½ÑƒÑ‚
                await asyncio.sleep(300)
                
                # Ð’Ñ‹Ð¿Ð¾Ð»Ð½ÑÐµÐ¼ Ð»ÐµÐ³ÐºÐ¸Ð¹ Ð·Ð°Ð¿Ñ€Ð¾Ñ Ð² Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ
                # Ð­Ñ‚Ð¾ Ð·Ð°ÑÑ‚Ð°Ð²Ð»ÑÐµÑ‚ ÐžÐ¡ Ð¿Ð¾Ð´Ð´ÐµÑ€Ð¶Ð¸Ð²Ð°Ñ‚ÑŒ ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ðµ Ð°ÐºÑ‚Ð¸Ð²Ð½Ñ‹Ð¼
                await self._run_sync(self._ping_db)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Keepalive ping failed: {e}")

    def _ping_db(self):
        """Ð¡Ð¸Ð½Ñ…Ñ€Ð¾Ð½Ð½Ð°Ñ Ñ„ÑƒÐ½ÐºÑ†Ð¸Ñ Ð´Ð»Ñ Ð¿Ð¸Ð½Ð³Ð° (Ð²Ñ‹Ð·Ñ‹Ð²Ð°ÐµÑ‚ÑÑ Ð¸Ð· _db_keepalive_loop)"""
        try:
            with self.db.get_connection() as conn:
                conn.execute("SELECT 1").fetchone()
        except:
            pass

    def _ping_db_query(self):
        """Ð¡Ð¸Ð½Ñ…Ñ€Ð¾Ð½Ð½Ð°Ñ Ñ„ÑƒÐ½ÐºÑ†Ð¸Ñ Ð´Ð»Ñ Ð¿Ð¸Ð½Ð³Ð° (Ð²Ñ‹Ð¿Ð¾Ð»Ð½ÑÐµÑ‚ÑÑ Ð² run_sync)"""
        try:
            with self.db.get_connection() as conn:
                conn.execute("SELECT 1")
        except:
            pass

    async def _watchdog_loop(self):
        """Watchdog: Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ Ð·Ð´Ð¾Ñ€Ð¾Ð²ÑŒÑ ÑÐµÑ€Ð²ÐµÑ€Ð°, Ð¾Ñ‡Ð¸ÑÑ‚ÐºÐ° Ð¼Ñ‘Ñ€Ñ‚Ð²Ñ‹Ñ… ÑÐµÑÑÐ¸Ð¹, Ð»Ð¾Ð³Ð¸Ñ€Ð¾Ð²Ð°Ð½Ð¸Ðµ ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸Ñ."""
        logger.info("Server watchdog started")
        while True:
            try:
                # Ð—Ð°Ð¼ÐµÑ€ÑÐµÐ¼ Ð»Ð°Ð³ event loop (ÐµÑÐ»Ð¸ > 5Ñ â€” event loop Ð±Ñ‹Ð» Ð·Ð°Ð±Ð»Ð¾ÐºÐ¸Ñ€Ð¾Ð²Ð°Ð½)
                t0 = time.monotonic()
                await asyncio.sleep(60)  # ÐŸÑ€Ð¾Ð²ÐµÑ€ÐºÐ° ÐºÐ°Ð¶Ð´ÑƒÑŽ Ð¼Ð¸Ð½ÑƒÑ‚Ñƒ
                loop_lag = time.monotonic() - t0 - 60.0
                if loop_lag > 5.0:
                    logger.warning(f"[WATCHDOG] Event loop lag detected: {loop_lag:.1f}s (expected ~0s)")
                elif loop_lag > 1.0:
                    logger.info(f"[WATCHDOG] Event loop minor lag: {loop_lag:.1f}s")

                # 0. Periodic audit retention cleanup (once per hour)
                now_ts = time.time()
                if (self._last_audit_cleanup_at is None) or (now_ts - float(self._last_audit_cleanup_at) >= 3600):
                    removed = await self._run_sync(self._cleanup_old_user_action_logs)
                    self._last_audit_cleanup_at = now_ts
                    if removed:
                        logger.info(f"[AUDIT] Old action logs removed: {removed}")

                # 1. Ð¡Ñ‡Ð¸Ñ‚Ð°ÐµÐ¼ Ð¶Ð¸Ð²Ñ‹Ñ…/Ð¼Ñ‘Ñ€Ñ‚Ð²Ñ‹Ñ… ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²
                dead_sessions = []
                for session_id, session in list(self.sessions.sessions.items()):
                    ws = session.websocket
                    try:
                        # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼, Ð¶Ð¸Ð² Ð»Ð¸ websocket
                        if ws.closed:
                            dead_sessions.append(session_id)
                    except Exception:
                        dead_sessions.append(session_id)

                # 2. Ð£Ð´Ð°Ð»ÑÐµÐ¼ Ð¼Ñ‘Ñ€Ñ‚Ð²Ñ‹Ðµ ÑÐµÑÑÐ¸Ð¸
                for session_id in dead_sessions:
                    session = self.sessions.sessions.get(session_id)
                    if session:
                        logger.warning(f"Watchdog: removing dead session {session.username} ({session.role})")
                        self.sessions.remove_session(session.websocket)

                # 3. Ð›Ð¾Ð³Ð¸Ñ€ÑƒÐµÐ¼ ÑÐ¾ÑÑ‚Ð¾ÑÐ½Ð¸Ðµ ÑÐµÑ€Ð²ÐµÑ€Ð°
                active = len(self.sessions.sessions)
                admins = len(self.sessions.admin_clients)
                operators = len(self.sessions.operator_clients)
                warehouses = sum(len(c) for c in self.sessions.warehouse_clients.values())

                # ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ executor
                executor_info = ""
                if hasattr(self, '_monitor_executor'):
                    ex = self._monitor_executor
                    executor_info = f", executor_threads={ex._max_workers}"

                if dead_sessions or active > 0:
                    logger.info(
                        f"[WATCHDOG] Active: {active} (admin={admins}, op={operators}, wh={warehouses}), "
                        f"cleaned={len(dead_sessions)}{executor_info}"
                    )

                # 4. ÐŸÑ€Ð¾Ð²ÐµÑ€ÑÐµÐ¼ Ñ„Ð¾Ð½Ð¾Ð²Ñ‹Ðµ Ð·Ð°Ð´Ð°Ñ‡Ð¸
                for name, task in self._background_tasks.items():
                    if task.done():
                        exc = task.exception() if not task.cancelled() else None
                        if exc:
                            logger.error(f"[WATCHDOG] Background task '{name}' CRASHED: {exc}")
                        else:
                            logger.warning(f"[WATCHDOG] Background task '{name}' finished unexpectedly")
                        # ÐŸÐµÑ€ÐµÐ·Ð°Ð¿ÑƒÑÐºÐ°ÐµÐ¼ ÑƒÐ¿Ð°Ð²ÑˆÑƒÑŽ Ð·Ð°Ð´Ð°Ñ‡Ñƒ
                        restart_method = getattr(self, name, None)
                        if restart_method:
                            logger.info(f"[WATCHDOG] Restarting task '{name}'...")
                            self._background_tasks[name] = asyncio.create_task(restart_method())

            except Exception as e:
                logger.error(f"[WATCHDOG] Error: {e}")

    async def start(self):
        """Ð—Ð°Ð¿ÑƒÑÐº ÑÐµÑ€Ð²ÐµÑ€Ð°"""
        logger.info(f"Ð—Ð°Ð¿ÑƒÑÐº ÑÐµÑ€Ð²ÐµÑ€Ð° Ð½Ð° {HOST}:{PORT}")
        self._api_scan_lock = asyncio.Lock()
        # Ð’Ñ‹Ð´ÐµÐ»ÐµÐ½Ð½Ñ‹Ð¹ executor Ð´Ð»Ñ Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¾Ð² + DB-Ð¾Ð¿ÐµÑ€Ð°Ñ†Ð¸Ð¸ Ð¸Ð· async-Ñ…ÐµÐ½Ð´Ð»ÐµÑ€Ð¾Ð²
        # 10 Ð¿Ð¾Ñ‚Ð¾ÐºÐ¾Ð²: Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ñ‹ (CSV, Rechnung, API, Kunden) + DB-Ð·Ð°Ð¿Ñ€Ð¾ÑÑ‹ ÐºÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² + keepalive
        from concurrent.futures import ThreadPoolExecutor
        self._monitor_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="worker")

        # Ð£Ð²ÐµÐ»Ð¸Ñ‡Ð¸Ð²Ð°ÐµÐ¼ max_size Ð´Ð¾ 20 ÐœÐ‘, Ñ‡Ñ‚Ð¾Ð±Ñ‹ Ð¿Ð°ÐºÐµÑ‚Ñ‹ Ñ Ð·Ð°ÐºÐ°Ð·Ð°Ð¼Ð¸ Ð½Ðµ Ð¾Ð±Ñ€Ñ‹Ð²Ð°Ð»Ð¸ ÑÐ²ÑÐ·ÑŒ
        async with websockets.serve(
            self.handle_client,
            HOST,
            PORT,
            max_size=20_000_000,
            ping_interval=20,
            ping_timeout=20
        ):
            # Ð—Ð°Ð¿ÑƒÑÐºÐ°ÐµÐ¼ Ñ„Ð¾Ð½Ð¾Ð²Ñ‹Ðµ Ð·Ð°Ð´Ð°Ñ‡Ð¸ Ð¸ Ð¾Ñ‚ÑÐ»ÐµÐ¶Ð¸Ð²Ð°ÐµÐ¼ Ð¸Ñ… Ð´Ð»Ñ watchdog
            self._background_tasks = {}

            # 1. Ð¡Ð¸Ð½Ñ…Ñ€Ð¾Ð½Ð¸Ð·Ð°Ñ†Ð¸Ñ WooCommerce
            self._background_tasks['woocommerce_sync_loop'] = asyncio.create_task(self.woocommerce_sync_loop())

            # 2. ÐœÐ¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ CSV (Ð—ÐÐšÐÐ—Ð«)
            self._background_tasks['csv_monitor_loop'] = asyncio.create_task(self.csv_monitor_loop())

            # 3. ÐœÐ¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ Lieferschein â€” REMOVED (Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐ° Ñ‚ÐµÐ¿ÐµÑ€ÑŒ Ð² rechnung_monitor)

            # 4. ÐœÐ¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ ÑÑ‡ÐµÑ‚Ð¾Ð²
            self._background_tasks['rechnung_monitor_loop'] = asyncio.create_task(self.rechnung_monitor_loop())

            # 5. ÐœÐ¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ ÐšÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð² (KUNDEN)
            self._background_tasks['kunden_monitor_loop'] = asyncio.create_task(self.kunden_monitor_loop())

            # 6. ÐœÐ¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ Monolith API (Ð—ÐÐšÐÐ—Ð« Ð¸Ð· API, ÐºÐ°Ð¶Ð´Ñ‹Ðµ 10 Ð¼Ð¸Ð½)
            self._background_tasks['api_monitor_loop'] = asyncio.create_task(self.api_monitor_loop())

            # 7. Watchdog â€” Ð¼Ð¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ Ð·Ð´Ð¾Ñ€Ð¾Ð²ÑŒÑ
            self._background_tasks['_watchdog_loop'] = asyncio.create_task(self._watchdog_loop())

            # 8. DB Keepalive â€” Ð¿Ñ€ÐµÐ´Ð¾Ñ‚Ð²Ñ€Ð°Ñ‰ÐµÐ½Ð¸Ðµ Ð¿Ñ€Ð¾Ñ‚ÑƒÑ…Ð°Ð½Ð¸Ñ SMB-ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ñ
            self._background_tasks['_db_keepalive_loop'] = asyncio.create_task(self._db_keepalive_loop())

            # 9. Backup scheduler
            self._background_tasks['backup_scheduler_loop'] = asyncio.create_task(self.backup_scheduler_loop())

            logger.info("Ð¡ÐµÑ€Ð²ÐµÑ€ Ð·Ð°Ð¿ÑƒÑ‰ÐµÐ½ Ð¸ Ñ€Ð°Ð±Ð¾Ñ‚Ð°ÐµÑ‚!")
            logger.info(f"Ð Ð°Ð·Ñ€ÐµÑˆÐµÐ½Ð½Ñ‹Ð¹ Ñ€Ð°Ð·Ð¼ÐµÑ€ Ð¿Ð°ÐºÐµÑ‚Ð°: 20 ÐœÐ‘")
            logger.info(f"ÐœÐ¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ Ð—Ð°ÐºÐ°Ð·Ð¾Ð² CSV: {WISO_CSV_PATH}")
            logger.info(f"ÐœÐ¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ Ð—Ð°ÐºÐ°Ð·Ð¾Ð² API: {MONOLITH_API_URL}")
            logger.info(f"ÐœÐ¾Ð½Ð¸Ñ‚Ð¾Ñ€Ð¸Ð½Ð³ ÐšÐ»Ð¸ÐµÐ½Ñ‚Ð¾Ð²: {KUNDEN_CSV_PATH}")
            logger.info(f"Watchdog: Ð°ÐºÑ‚Ð¸Ð²ÐµÐ½ (60s interval)")
            logger.info(f"DB Keepalive: Ð°ÐºÑ‚Ð¸Ð²ÐµÐ½ (120s interval)")
            logger.info(f"Backup scheduler: Ð°ÐºÑ‚Ð¸Ð²ÐµÐ½ (30s interval)")

            await asyncio.Future()  # Ð Ð°Ð±Ð¾Ñ‚Ð°ÐµÐ¼ Ð²ÐµÑ‡Ð½Ð¾


# ============================================
# Ð—ÐÐŸÐ£Ð¡Ðš
# ============================================
def run_server(server_instance):
    """Ð¤ÑƒÐ½ÐºÑ†Ð¸Ñ Ð´Ð»Ñ Ð·Ð°Ð¿ÑƒÑÐºÐ° asyncio-ÑÐµÑ€Ð²ÐµÑ€Ð° Ð² Ð¾Ñ‚Ð´ÐµÐ»ÑŒÐ½Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ."""
    try:
        # Ð’Ð°Ð¶Ð½Ð¾ ÑÐ¾Ð·Ð´Ð°Ñ‚ÑŒ Ð½Ð¾Ð²Ñ‹Ð¹ event loop Ð´Ð»Ñ Ð¿Ð¾Ñ‚Ð¾ÐºÐ°
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Ð¡Ð¾Ñ…Ñ€Ð°Ð½ÑÐµÐ¼ ÑÑÑ‹Ð»ÐºÑƒ Ð½Ð° loop Ð´Ð»Ñ GUI (Ð¾Ñ‚ÐºÐ»ÑŽÑ‡ÐµÐ½Ð¸Ðµ Ð¿Ð¾Ð»ÑŒÐ·Ð¾Ð²Ð°Ñ‚ÐµÐ»ÐµÐ¹)
        server_instance.loop = loop
        loop.run_until_complete(server_instance.start())
    except Exception as e:
        logging.critical(f"ÐšÑ€Ð¸Ñ‚Ð¸Ñ‡ÐµÑÐºÐ°Ñ Ð¾ÑˆÐ¸Ð±ÐºÐ° Ð² Ð¿Ð¾Ñ‚Ð¾ÐºÐµ ÑÐµÑ€Ð²ÐµÑ€Ð°: {e}", exc_info=True)

if __name__ == "__main__":
    import threading
    # Ð¡ÐºÑ€Ñ‹Ð²Ð°ÐµÐ¼ ÐºÐ¾Ð½ÑÐ¾Ð»ÑŒÐ½Ð¾Ðµ Ð¾ÐºÐ½Ð¾ Ð½Ð° Windows (Ð¾ÑÑ‚Ð°Ð²Ð»ÑÐµÐ¼ Ñ‚Ð¾Ð»ÑŒÐºÐ¾ GUI),
    # ÐµÑÐ»Ð¸ ÑÐ²Ð½Ð¾ Ð½Ðµ Ð·Ð°Ð¿Ñ€Ð¾ÑˆÐµÐ½ Ñ€ÐµÐ¶Ð¸Ð¼ Ñ ÐºÐ¾Ð½ÑÐ¾Ð»ÑŒÑŽ.
    if os.name == 'nt' and os.environ.get('WISO_SHOW_CONSOLE', '0') != '1':
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        except Exception:
            pass

    # Ð˜Ð¼Ð¿Ð¾Ñ€Ñ‚Ð¸Ñ€ÑƒÐµÐ¼ GUI Ñ‚Ð¾Ð»ÑŒÐºÐ¾ Ð¿Ñ€Ð¸ Ð¿Ñ€ÑÐ¼Ð¾Ð¼ Ð·Ð°Ð¿ÑƒÑÐºÐµ
    from server_ui import ServerGUI  
    
    # 1. Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ ÑÐºÐ·ÐµÐ¼Ð¿Ð»ÑÑ€ ÑÐµÑ€Ð²ÐµÑ€Ð° (Ð»Ð¾Ð³Ð¸ÐºÐ°)
    server = UnifiedServer()
    
    # 2. Ð¡Ð¾Ð·Ð´Ð°ÐµÐ¼ Ð³Ñ€Ð°Ñ„Ð¸Ñ‡ÐµÑÐºÐ¸Ð¹ Ð¸Ð½Ñ‚ÐµÑ€Ñ„ÐµÐ¹Ñ
    gui_app = ServerGUI(server, title="WISO GoLabel Server v2.0")
    
    # 3. Ð—Ð°Ð¿ÑƒÑÐºÐ°ÐµÐ¼ ÑÐµÑ€Ð²ÐµÑ€ Ð² Ñ„Ð¾Ð½Ð¾Ð²Ð¾Ð¼ Ð¿Ð¾Ñ‚Ð¾ÐºÐµ
    server_thread = threading.Thread(target=run_server, args=(server,), daemon=True)
    server_thread.start()
    
    logging.info("Ð¡ÐµÑ€Ð²ÐµÑ€ Ð·Ð°Ð¿ÑƒÑÐºÐ°ÐµÑ‚ÑÑ...")
    logging.info(f"Ð‘Ð°Ð·Ð° Ð´Ð°Ð½Ð½Ñ‹Ñ…: {DB_PATH}")
    
    # 4. Ð—Ð°Ð¿ÑƒÑÐºÐ°ÐµÐ¼ Ð³Ð»Ð°Ð²Ð½Ñ‹Ð¹ Ñ†Ð¸ÐºÐ» Ð¾ÐºÐ½Ð°
    try:
        gui_app.mainloop()
    except KeyboardInterrupt:
        pass
    
    logging.info("Ð¡ÐµÑ€Ð²ÐµÑ€ Ð¾ÑÑ‚Ð°Ð½Ð¾Ð²Ð»ÐµÐ½.")
