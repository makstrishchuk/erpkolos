#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Client Stock Service — fetches and caches stock data from external Monolith API.
Provides pivoted table data for the Client Stock Viewer frontend.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

import httpx

logger = logging.getLogger(__name__)

# API endpoints
FULL_STOCK_URL = "https://api.monolith-gruppe.de/api/ZolotojKolos/stockCheck"
ACTUAL_STOCK_URL = "https://api.monolith-gruppe.de/api/ZolotojKolos/stockCheck/trim"

# Refresh interval in seconds (10 minutes)
REFRESH_INTERVAL = 600
# HTTP request timeout in seconds
REQUEST_TIMEOUT = 30

# Known regions extracted from supplier names
KNOWN_REGIONS = ["Mitte", "Nord", "Süd", "West", "Ost", "International"]


class ClientStockService:
    """Fetches, caches, and transforms client stock data from the Monolith API."""

    def __init__(self):
        self._full_stock_cache: Optional[Dict[str, Any]] = None
        self._actual_stock_cache: Optional[Dict[str, Any]] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        self._running = False

    async def start(self):
        """Initialize HTTP client and start background refresh loop."""
        self._http_client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        self._running = True
        # Initial fetch
        await self._refresh_all()
        # Start background loop
        asyncio.create_task(self._refresh_loop())
        logger.info("ClientStockService started, refresh every %d seconds", REFRESH_INTERVAL)

    async def stop(self):
        """Graceful shutdown."""
        self._running = False
        if self._http_client:
            await self._http_client.aclose()

    async def _refresh_loop(self):
        """Background loop that refreshes cache every REFRESH_INTERVAL seconds."""
        while self._running:
            await asyncio.sleep(REFRESH_INTERVAL)
            if not self._running:
                break
            await self._refresh_all()

    async def _refresh_all(self):
        """Fetch both endpoints and update caches."""
        self._full_stock_cache = await self._fetch_and_transform(
            FULL_STOCK_URL, self._full_stock_cache
        )
        self._actual_stock_cache = await self._fetch_and_transform(
            ACTUAL_STOCK_URL, self._actual_stock_cache
        )

    async def _fetch_and_transform(
        self, url: str, fallback_cache: Optional[Dict]
    ) -> Optional[Dict]:
        """Fetch data from URL, transform to pivoted format.
        On failure, returns the previous cache so stale data remains available."""
        try:
            response = await self._http_client.get(url)
            response.raise_for_status()
            raw_data = response.json()
            transformed = self._transform_data(raw_data)
            logger.info(
                "Fetched %s — %d items", url.split("/")[-1], len(raw_data)
            )
            return transformed
        except httpx.TimeoutException:
            logger.error("Timeout fetching %s", url)
        except httpx.HTTPStatusError as e:
            logger.error("HTTP %d from %s", e.response.status_code, url)
        except Exception as e:
            logger.error("Error fetching %s: %s", url, e)
        return fallback_cache

    @staticmethod
    def _extract_region(lieferant_name: str) -> str:
        """Extract region keyword from supplier name.
        'Monolith Mitte GmbH' -> 'Mitte'"""
        for region in KNOWN_REGIONS:
            if region.lower() in lieferant_name.lower():
                return region
        return lieferant_name.strip()

    @staticmethod
    def _transform_data(raw_data: List[Dict]) -> Dict[str, Any]:
        """Pivot raw API JSON into a table structure.

        Input:  [{artikel_nr, artikel_bezeichnung, lieferanten: [{lieferant_name, quantity}]}]
        Output: {last_updated, headers: [...], items: [{...}]}
        """
        # 1) Discover all unique regions
        all_regions: set = set()
        for article in raw_data:
            for supplier in article.get("lieferanten", []):
                region = ClientStockService._extract_region(
                    supplier.get("lieferant_name", "")
                )
                all_regions.add(region)

        sorted_regions = sorted(all_regions)

        # 2) Build column headers
        headers = ["Артикул", "Наименование"] + sorted_regions + ["Итого"]

        # 3) Build row data
        items: List[Dict[str, Any]] = []
        for article in raw_data:
            row: Dict[str, Any] = {
                "Артикул": article.get("artikel_nr", ""),
                "Наименование": article.get("artikel_bezeichnung", ""),
            }
            total = 0
            for region in sorted_regions:
                row[region] = 0
            for supplier in article.get("lieferanten", []):
                region = ClientStockService._extract_region(
                    supplier.get("lieferant_name", "")
                )
                qty = supplier.get("quantity", 0) or 0
                row[region] = qty
                total += qty
            row["Итого"] = total
            items.append(row)

        return {
            "last_updated": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "headers": headers,
            "items": items,
        }

    def get_full_stock_data(self) -> Dict[str, Any]:
        """Return cached full stock data."""
        if self._full_stock_cache:
            return self._full_stock_cache
        return {"last_updated": None, "headers": [], "items": []}

    def get_actual_stock_data(self) -> Dict[str, Any]:
        """Return cached actual (trimmed) stock data."""
        if self._actual_stock_cache:
            return self._actual_stock_cache
        return {"last_updated": None, "headers": [], "items": []}
