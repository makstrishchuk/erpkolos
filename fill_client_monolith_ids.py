#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fill missing client_routes.monolith_client_id from Monolith customer export CSV.

Safe matching strategy (applies only unique/high-confidence matches):
1) exact normalized (name + city)
2) exact normalized (address + city), only when both are non-empty
3) exact normalized name (unique)
4) market key match: ("mix markt"/"mini mix"/"prima markt"/"neo markt", number)
   with city first, then unique key globally
5) fuzzy fallback with strict thresholds and uniqueness gap

Writes a detailed report CSV to generated/monolith_id_reports/.
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "wiso_golabel.db"
DEFAULT_SOURCE = ROOT / "kundenliste_export.12.03.26.csv"
REPORT_DIR = ROOT / "generated" / "monolith_id_reports"


def normalize_text(value: str) -> str:
    s = (value or "").strip().lower()
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def normalize_article_like(value: str) -> str:
    raw = str(value or "").strip().replace(" ", "").replace(",", "")
    if "." in raw and raw.replace(".", "").isdigit():
        raw = raw.split(".", 1)[0]
    return raw.zfill(5) if raw.isdigit() else raw


def city_from_ort(ort: str) -> str:
    o = (ort or "").strip()
    m = re.match(r"^\s*\d{4,6}\s+(.+)$", o)
    return (m.group(1).strip() if m else o)


def market_key(name: str) -> Tuple[str, str]:
    n = normalize_text(name)
    market_types = ("mix markt", "mini mix", "prima markt", "neo markt")
    for market_type in market_types:
        m = re.search(r"\b" + re.escape(market_type) + r"\s*0*([0-9]{1,5})\b", n)
        if m:
            return market_type, str(int(m.group(1)))
    return "", ""


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    sa = set(a.split())
    sb = set(b.split())
    jac = (len(sa & sb) / len(sa | sb)) if sa and sb else 0.0
    seq = SequenceMatcher(None, a, b).ratio()
    return 0.6 * seq + 0.4 * jac


@dataclass
class SourceClient:
    monolith_id: str
    raw_name: str
    raw_addr: str
    raw_ort: str
    norm_name: str
    norm_addr: str
    norm_city: str
    key_market_type: str
    key_market_num: str


@dataclass
class LocalClient:
    client_id: str
    monolith_client_id: str
    raw_name: str
    raw_addr: str
    raw_city: str
    norm_name: str
    norm_addr: str
    norm_city: str
    key_market_type: str
    key_market_num: str


def parse_source_csv(path: Path) -> List[SourceClient]:
    with open(path, "r", encoding="latin-1", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
        except Exception:
            delim = ";"
        reader = csv.DictReader(f, delimiter=delim)
        out: List[SourceClient] = []
        for row in reader:
            monolith_id = (row.get("ID") or "").strip()
            if not monolith_id:
                continue
            name = (row.get("Kunde") or "").strip()
            addr = (row.get("Adresse") or "").strip()
            ort = (row.get("Ort") or "").strip()
            city = city_from_ort(ort)
            mk_type, mk_num = market_key(name)
            out.append(
                SourceClient(
                    monolith_id=monolith_id,
                    raw_name=name,
                    raw_addr=addr,
                    raw_ort=ort,
                    norm_name=normalize_text(name),
                    norm_addr=normalize_text(addr),
                    norm_city=normalize_text(city),
                    key_market_type=mk_type,
                    key_market_num=mk_num,
                )
            )
        return out


def load_local_clients_missing_monolith(db_path: Path) -> List[LocalClient]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT client_id, client_name, address, city, monolith_client_id
        FROM client_routes
        WHERE monolith_client_id IS NULL OR TRIM(monolith_client_id) = ''
        ORDER BY client_id
        """
    ).fetchall()
    conn.close()

    out: List[LocalClient] = []
    for r in rows:
        name = str(r["client_name"] or "").strip()
        addr = str(r["address"] or "").strip()
        city = str(r["city"] or "").strip()
        mk_type, mk_num = market_key(name)
        out.append(
            LocalClient(
                client_id=str(r["client_id"] or "").strip(),
                monolith_client_id=str(r["monolith_client_id"] or "").strip(),
                raw_name=name,
                raw_addr=addr,
                raw_city=city,
                norm_name=normalize_text(name),
                norm_addr=normalize_text(addr),
                norm_city=normalize_text(city),
                key_market_type=mk_type,
                key_market_num=mk_num,
            )
        )
    return out


def build_indexes(
    source_rows: List[SourceClient],
) -> Tuple[
    Dict[Tuple[str, str], List[SourceClient]],
    Dict[Tuple[str, str], List[SourceClient]],
    Dict[str, List[SourceClient]],
    Dict[Tuple[str, str], List[SourceClient]],
]:
    by_name_city: Dict[Tuple[str, str], List[SourceClient]] = {}
    by_addr_city: Dict[Tuple[str, str], List[SourceClient]] = {}
    by_name: Dict[str, List[SourceClient]] = {}
    by_market: Dict[Tuple[str, str], List[SourceClient]] = {}

    for s in source_rows:
        by_name_city.setdefault((s.norm_name, s.norm_city), []).append(s)
        if s.norm_addr and s.norm_city:
            by_addr_city.setdefault((s.norm_addr, s.norm_city), []).append(s)
        by_name.setdefault(s.norm_name, []).append(s)
        if s.key_market_type and s.key_market_num:
            by_market.setdefault((s.key_market_type, s.key_market_num), []).append(s)

    return by_name_city, by_addr_city, by_name, by_market


def choose_one(candidates: List[SourceClient]) -> Optional[SourceClient]:
    return candidates[0] if len(candidates) == 1 else None


def match_client(
    c: LocalClient,
    source_rows: List[SourceClient],
    by_name_city: Dict[Tuple[str, str], List[SourceClient]],
    by_addr_city: Dict[Tuple[str, str], List[SourceClient]],
    by_name: Dict[str, List[SourceClient]],
    by_market: Dict[Tuple[str, str], List[SourceClient]],
    fuzzy_threshold: float,
    fuzzy_gap: float,
) -> Tuple[Optional[SourceClient], str, float]:
    # 1) exact name+city
    if c.norm_name and c.norm_city:
        found = choose_one(by_name_city.get((c.norm_name, c.norm_city), []))
        if found:
            return found, "name_city", 1.0

    # 2) exact addr+city
    if c.norm_addr and c.norm_city:
        found = choose_one(by_addr_city.get((c.norm_addr, c.norm_city), []))
        if found:
            return found, "addr_city", 1.0

    # 3) exact name
    if c.norm_name:
        found = choose_one(by_name.get(c.norm_name, []))
        if found:
            return found, "name", 1.0

    # 4) market key
    if c.key_market_type and c.key_market_num:
        market_candidates = list(by_market.get((c.key_market_type, c.key_market_num), []))
        if c.norm_city:
            city_candidates = [x for x in market_candidates if x.norm_city == c.norm_city]
            found = choose_one(city_candidates)
            if found:
                return found, "market_city", 1.0
        found = choose_one(market_candidates)
        if found:
            return found, "market", 1.0

    # 5) fuzzy fallback
    if c.norm_city:
        candidates = [x for x in source_rows if x.norm_city == c.norm_city]
        if not candidates:
            candidates = source_rows
    else:
        candidates = source_rows

    scored: List[Tuple[float, SourceClient]] = []
    for s in candidates:
        score_name = similarity(c.norm_name, s.norm_name)
        score_addr_city = similarity(
            f"{c.norm_addr} {c.norm_city}".strip(),
            f"{s.norm_addr} {s.norm_city}".strip(),
        )
        score = 0.7 * score_name + 0.3 * score_addr_city
        if score >= fuzzy_threshold:
            scored.append((score, s))

    if not scored:
        return None, "no_match", 0.0

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_src = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if (best_score - second_score) >= fuzzy_gap:
        return best_src, "fuzzy", best_score
    return None, "ambiguous", best_score


def apply_updates(db_path: Path, updates: Iterable[Tuple[str, str]]) -> int:
    rows = [(mid, datetime.now().isoformat(), cid) for cid, mid in updates]
    if not rows:
        return 0
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executemany(
        """
        UPDATE client_routes
        SET monolith_client_id = ?, updated_at = ?
        WHERE client_id = ?
          AND (monolith_client_id IS NULL OR TRIM(monolith_client_id) = '')
        """,
        rows,
    )
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return changed


def main():
    parser = argparse.ArgumentParser(description="Fill missing monolith_client_id for local clients.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--apply", action="store_true", help="Apply updates to DB. Without flag: dry-run only.")
    parser.add_argument("--fuzzy-threshold", type=float, default=0.90)
    parser.add_argument("--fuzzy-gap", type=float, default=0.06)
    args = parser.parse_args()

    source_rows = parse_source_csv(args.source)
    local_missing = load_local_clients_missing_monolith(args.db)
    by_name_city, by_addr_city, by_name, by_market = build_indexes(source_rows)

    stats = {
        "total_missing_before": len(local_missing),
        "matched_name_city": 0,
        "matched_addr_city": 0,
        "matched_name": 0,
        "matched_market_city": 0,
        "matched_market": 0,
        "matched_fuzzy": 0,
        "ambiguous": 0,
        "no_match": 0,
        "to_update": 0,
        "applied": 0,
    }

    updates: List[Tuple[str, str]] = []  # (client_id, monolith_id)
    report_rows: List[dict] = []

    for c in local_missing:
        matched, reason, score = match_client(
            c,
            source_rows,
            by_name_city,
            by_addr_city,
            by_name,
            by_market,
            args.fuzzy_threshold,
            args.fuzzy_gap,
        )

        if matched:
            updates.append((c.client_id, matched.monolith_id))
            stats[f"matched_{reason}"] = stats.get(f"matched_{reason}", 0) + 1
        else:
            stats[reason] = stats.get(reason, 0) + 1

        report_rows.append(
            {
                "client_id": c.client_id,
                "client_name": c.raw_name,
                "client_city": c.raw_city,
                "client_address": c.raw_addr,
                "match_status": "matched" if matched else reason,
                "match_reason": reason,
                "match_score": f"{score:.4f}" if score else "",
                "monolith_id": matched.monolith_id if matched else "",
                "source_name": matched.raw_name if matched else "",
                "source_city": city_from_ort(matched.raw_ort) if matched else "",
                "source_address": matched.raw_addr if matched else "",
            }
        )

    # Remove duplicate monolith IDs from updates (keep first by sorted client_id)
    updates_sorted = sorted(updates, key=lambda t: normalize_article_like(t[0]))
    unique_updates: List[Tuple[str, str]] = []
    used_monolith_ids = set()
    for cid, mid in updates_sorted:
        if mid in used_monolith_ids:
            continue
        used_monolith_ids.add(mid)
        unique_updates.append((cid, mid))

    stats["to_update"] = len(unique_updates)

    if args.apply:
        stats["applied"] = apply_updates(args.db, unique_updates)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"monolith_id_fill_report_{ts}.csv"
    with open(report_path, "w", encoding="utf-8", newline="") as f:
        cols = [
            "client_id",
            "client_name",
            "client_city",
            "client_address",
            "match_status",
            "match_reason",
            "match_score",
            "monolith_id",
            "source_name",
            "source_city",
            "source_address",
        ]
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";")
        w.writeheader()
        w.writerows(report_rows)

    print("=== Monolith ID Fill ===")
    print(f"DB: {args.db}")
    print(f"Source CSV: {args.source}")
    print(f"Dry-run: {'no' if args.apply else 'yes'}")
    for k in sorted(stats.keys()):
        print(f"{k}: {stats[k]}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()

