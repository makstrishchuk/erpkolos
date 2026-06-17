#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mass-import client emails from Monolith CSV into client_routes.

Matching strategy:
1) Exact by monolith_client_id <-> CSV ID.
2) Fuzzy by client name + address (threshold, default 0.75) with candidate blocking.

Writes a detailed CSV report to generated/email_import_reports/.
"""

import argparse
import csv
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "wiso_golabel.db"
DEFAULT_SOURCE = ROOT / "kundenliste_export.12.03.26.csv"
REPORT_DIR = ROOT / "generated" / "email_import_reports"


@dataclass
class SourceRow:
    monolith_id: str
    name: str
    address: str
    city_plz: str
    city: str
    plz: str
    email: str
    norm_name: str
    norm_addr: str


@dataclass
class LocalClient:
    client_id: str
    monolith_client_id: str
    name: str
    address: str
    plz: str
    city: str
    email: str
    norm_name: str
    norm_addr: str
    mix_num: str


def normalize_text(value: str) -> str:
    s = (value or "").strip().lower()
    repl = {
        "ß": "ss",
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "é": "e",
        "è": "e",
        "á": "a",
        "ó": "o",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    s = s.replace("straße", "str").replace("strasse", "str").replace("str.", "str")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_plz(city_plz: str) -> str:
    m = re.search(r"\b(\d{5})\b", city_plz or "")
    return m.group(1) if m else ""


def extract_mix_number(name: str) -> str:
    s = normalize_text(name)
    m = re.search(r"\bmix\s*markt\s*0*([0-9]{1,5})\b", s)
    if m:
        return str(int(m.group(1)))
    return ""


def ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def token_jaccard(a: str, b: str) -> float:
    sa = set((a or "").split())
    sb = set((b or "").split())
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def blended_similarity(a: str, b: str) -> float:
    # More stable than pure SequenceMatcher for reordered words.
    return 0.6 * ratio(a, b) + 0.4 * token_jaccard(a, b)


def parse_source_csv(path: Path) -> List[SourceRow]:
    rows: List[SourceRow] = []
    with open(path, "r", encoding="latin-1", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            email = (row.get("Email") or "").strip()
            if "@" not in email:
                continue
            monolith_id = (row.get("ID") or "").strip()
            name = (row.get("Kunde") or "").strip()
            address = (row.get("Adresse") or "").strip()
            city_plz = (row.get("Ort") or "").strip()
            plz = extract_plz(city_plz)
            city = city_plz
            if plz:
                city = re.sub(r"^\s*" + re.escape(plz) + r"\s*", "", city_plz).strip()
            rows.append(
                SourceRow(
                    monolith_id=monolith_id,
                    name=name,
                    address=address,
                    city_plz=city_plz,
                    city=city,
                    plz=plz,
                    email=email,
                    norm_name=normalize_text(name),
                    norm_addr=normalize_text(f"{address} {plz} {city}"),
                )
            )
    return rows


def load_local_clients(db_path: Path) -> List[LocalClient]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT client_id, client_name, address, plz, city, email, monolith_client_id
        FROM client_routes
        ORDER BY client_id
        """
    ).fetchall()
    conn.close()
    out: List[LocalClient] = []
    for r in rows:
        name = str(r["client_name"] or "").strip()
        address = str(r["address"] or "").strip()
        plz = str(r["plz"] or "").strip()
        city = str(r["city"] or "").strip()
        out.append(
            LocalClient(
                client_id=str(r["client_id"] or "").strip(),
                monolith_client_id=str(r["monolith_client_id"] or "").strip(),
                name=name,
                address=address,
                plz=plz,
                city=city,
                email=str(r["email"] or "").strip(),
                norm_name=normalize_text(name),
                norm_addr=normalize_text(f"{address} {plz} {city}"),
                mix_num=extract_mix_number(name),
            )
        )
    return out


def build_indexes(source_rows: List[SourceRow]) -> Tuple[Dict[str, SourceRow], Dict[str, List[SourceRow]], Dict[str, List[SourceRow]]]:
    by_id: Dict[str, SourceRow] = {}
    by_plz: Dict[str, List[SourceRow]] = {}
    by_mix_num: Dict[str, List[SourceRow]] = {}
    for r in source_rows:
        if r.monolith_id and r.monolith_id not in by_id:
            by_id[r.monolith_id] = r
        if r.plz:
            by_plz.setdefault(r.plz, []).append(r)
        m = extract_mix_number(r.name)
        if m:
            by_mix_num.setdefault(m, []).append(r)
    return by_id, by_plz, by_mix_num


def pick_best_match(
    client: LocalClient,
    by_id: Dict[str, SourceRow],
    by_plz: Dict[str, List[SourceRow]],
    by_mix_num: Dict[str, List[SourceRow]],
    all_source: List[SourceRow],
    threshold: float,
    min_delta: float,
) -> Tuple[Optional[SourceRow], str, float, float, float]:
    # Exact match by Monolith ID first.
    if client.monolith_client_id and client.monolith_client_id in by_id:
        src = by_id[client.monolith_client_id]
        return src, "exact_id", 1.0, 1.0, 1.0

    candidates: List[SourceRow] = []
    if client.plz and client.plz in by_plz:
        candidates.extend(by_plz[client.plz])
    if client.mix_num and client.mix_num in by_mix_num:
        candidates.extend(by_mix_num[client.mix_num])
    if not candidates:
        # Fallback: still bounded slice to avoid expensive full scan in most cases.
        candidates = all_source[:]

    # De-duplicate preserving order.
    seen = set()
    uniq: List[SourceRow] = []
    for c in candidates:
        key = (c.monolith_id, c.email)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    scored: List[Tuple[float, float, float, SourceRow]] = []
    for src in uniq:
        name_score = blended_similarity(client.norm_name, src.norm_name)
        addr_score = blended_similarity(client.norm_addr, src.norm_addr)
        score = 0.6 * name_score + 0.4 * addr_score
        if score >= threshold:
            scored.append((score, name_score, addr_score, src))

    if not scored:
        return None, "no_match", 0.0, 0.0, 0.0

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if (best[0] - second_score) < min_delta:
        return None, "ambiguous", best[0], best[1], best[2]
    return best[3], "fuzzy", best[0], best[1], best[2]


def run_import(db_path: Path, source_csv: Path, threshold: float, min_delta: float, apply: bool) -> Path:
    source_rows = parse_source_csv(source_csv)
    clients = load_local_clients(db_path)
    by_id, by_plz, by_mix_num = build_indexes(source_rows)

    report_rows = []
    updates: List[Tuple[str, str]] = []
    stats = {
        "total_clients": len(clients),
        "already_email": 0,
        "matched_exact_id": 0,
        "matched_fuzzy": 0,
        "ambiguous": 0,
        "no_match": 0,
        "to_update": 0,
    }

    for c in clients:
        if c.email:
            stats["already_email"] += 1
            report_rows.append(
                {
                    "client_id": c.client_id,
                    "client_name": c.name,
                    "status": "already_has_email",
                    "current_email": c.email,
                    "new_email": "",
                    "method": "",
                    "score": "",
                    "name_score": "",
                    "address_score": "",
                    "local_monolith_id": c.monolith_client_id,
                    "source_monolith_id": "",
                    "source_name": "",
                    "source_address": "",
                }
            )
            continue

        src, method, score, n_score, a_score = pick_best_match(
            c, by_id, by_plz, by_mix_num, source_rows, threshold, min_delta
        )

        if src is None:
            status = "ambiguous" if method == "ambiguous" else "no_match"
            stats[status] += 1
            report_rows.append(
                {
                    "client_id": c.client_id,
                    "client_name": c.name,
                    "status": status,
                    "current_email": "",
                    "new_email": "",
                    "method": method,
                    "score": f"{score:.4f}" if score else "",
                    "name_score": f"{n_score:.4f}" if n_score else "",
                    "address_score": f"{a_score:.4f}" if a_score else "",
                    "local_monolith_id": c.monolith_client_id,
                    "source_monolith_id": "",
                    "source_name": "",
                    "source_address": "",
                }
            )
            continue

        if method == "exact_id":
            stats["matched_exact_id"] += 1
        else:
            stats["matched_fuzzy"] += 1

        updates.append((src.email, c.client_id))
        report_rows.append(
            {
                "client_id": c.client_id,
                "client_name": c.name,
                "status": "matched",
                "current_email": "",
                "new_email": src.email,
                "method": method,
                "score": f"{score:.4f}",
                "name_score": f"{n_score:.4f}",
                "address_score": f"{a_score:.4f}",
                "local_monolith_id": c.monolith_client_id,
                "source_monolith_id": src.monolith_id,
                "source_name": src.name,
                "source_address": f"{src.address}, {src.city_plz}".strip(", "),
            }
        )

    stats["to_update"] = len(updates)

    if apply and updates:
        conn = sqlite3.connect(db_path)
        conn.executemany(
            "UPDATE client_routes SET email = ?, updated_at = ? WHERE client_id = ?",
            [(email, datetime.now().isoformat(), client_id) for email, client_id in updates],
        )
        conn.commit()
        conn.close()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"email_import_report_{ts}.csv"
    with open(report_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "client_id",
            "client_name",
            "status",
            "current_email",
            "new_email",
            "method",
            "score",
            "name_score",
            "address_score",
            "local_monolith_id",
            "source_monolith_id",
            "source_name",
            "source_address",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        w.writeheader()
        for row in report_rows:
            w.writerow(row)

    print(f"Source rows with email: {len(source_rows)}")
    print(f"Total clients in DB: {stats['total_clients']}")
    print(f"Already had email: {stats['already_email']}")
    print(f"Matched exact by monolith ID: {stats['matched_exact_id']}")
    print(f"Matched fuzzy: {stats['matched_fuzzy']}")
    print(f"Ambiguous: {stats['ambiguous']}")
    print(f"No match: {stats['no_match']}")
    print(f"Planned updates: {stats['to_update']}")
    print(f"Applied to DB: {'yes' if apply else 'no (dry-run)'}")
    print(f"Report: {report_path}")

    return report_path


def main():
    parser = argparse.ArgumentParser(description="Import client emails into client_routes.")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to SQLite DB")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Source CSV path")
    parser.add_argument("--threshold", type=float, default=0.75, help="Fuzzy threshold (0..1)")
    parser.add_argument("--min-delta", type=float, default=0.05, help="Min score gap to avoid ambiguity")
    parser.add_argument("--apply", action="store_true", help="Apply updates to DB")
    args = parser.parse_args()

    run_import(args.db, args.source, args.threshold, args.min_delta, args.apply)


if __name__ == "__main__":
    main()

