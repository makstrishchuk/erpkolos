"""
Backend services for WISO GoLabel ERP System
"""

__version__ = "1.0.0"

from .database import Database, User
from .resource_manager import ResourceManager
from .logistics_manager import LogisticsManager
from .stock_manager import VirtualStockManager
from .production_planner import ProductionPlanner

# ClientStockService requires httpx (only used by server/server.py, not server_unified.py)
try:
    from .stock_service import ClientStockService
except ImportError:
    ClientStockService = None

__all__ = [
    'Database',
    'User',
    'ResourceManager',
    'LogisticsManager',
    'VirtualStockManager',
    'ProductionPlanner',
    'ClientStockService',
]
