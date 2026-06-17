#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Second-pass refinement for clients still without email.

Applies only high-confidence matches and generates a review CSV with top candidates.
"""

import argparse
import csv
import re
import sqlite3
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "wiso_golabel.db"
SOURCE_CSV = ROOT / "kundenliste_export.12.03.26.csv"
OUT_DIR = ROOT / "generated" / "email_import_reports"


def norm(s: str) -> str:
    s = (s or "").strip().lower()
    for k, v in {"ß": "ss", "ä": "ae", "ö": "oe", "ü": "ue", "é": "e", "è": "e"}.items():
        s = s.replace(k, v)
    s = s.replace("straße", "str").replace("strasse", "str").replace("str.", "str")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def mix_number(name: str) -> str:
    m = re.search(r"\bmix\s*markt\s*0*([0-9]{1,5})\b", norm(name))
    return str(int(m.group(1))) if m else ""


def plz_from_ort(ort: str) -> str:
    m = re.search(r"\b(\d{5})\b", ort or "")
    return m.group(1) if m else ""


def sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    sa = set(a.split())
    sb = set(b.split())
    jac = (len(sa & sb) / len(sa | sb)) if sa and sb else 0.0
    return 0.6 * SequenceMatcher(None, a, b).ratio() + 0.4 * jac


def load_source(path: Path) -> List[Dict[str, str]]:
    out = []
    with open(path, "r", encoding="latin-1", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            email = (row.get("Email") or "").strip()
            if "@" not in email:
                continue
            name = (row.get("Kunde") or "").strip()
            addr = (row.get("Adresse") or "").strip()
            ort = (row.get("Ort") or "").strip()
            out.append(
                {
                    "id": (row.get("ID") or "").strip(),
                    "name": name,
                    "addr": addr,
                    "ort": ort,
                    "plz": plz_from_ort(ort),
                    "mix": mix_number(name),
                    "email": email,
                    "n_name": norm(name),
                    "n_addr": norm(f"{addr} {ort}"),
                }
            )
    return out


def load_clients_without_email(db_path: Path) -> List[Dict[str, str]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT client_id, client_name, address, plz, city
        FROM client_routes
        WHERE trim(coalesce(email, '')) = ''
        ORDER BY client_id
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def score_client(c: Dict[str, str], src: Dict[str, str]) -> Tuple[float, float, float]:
    n_name = norm(c.get("client_name", ""))
    n_addr = norm(f"{c.get('address', '')} {c.get('plz', '')} {c.get('city', '')}")
    name_score = sim(n_name, src["n_name"])
    addr_score = sim(n_addr, src["n_addr"])
    score = 0.65 * name_score + 0.35 * addr_score
    if c.get("plz") and src.get("plz") and c["plz"] == src["plz"]:
        score += 0.03
    cmix = mix_number(c.get("client_name", ""))
    if cmix and src.get("mix") and cmix == src["mix"]:
        score += 0.04
    return score, name_score, addr_score


def main():
    parser = argparse.ArgumentParser(description="Second pass email refinement")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--source", type=Path, default=SOURCE_CSV)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    source = load_source(args.source)
    clients = load_clients_without_email(args.db)

    auto_updates: List[Tuple[str, str, str, float]] = []
    review_rows = []

    for c in clients:
        scored = []
        for s in source:
            score, name_score, addr_score = score_client(c, s)
            scored.append((score, name_score, addr_score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[0] if scored else None
        second = scored[1] if len(scored) > 1 else None
        third = scored[2] if len(scored) > 2 else None

        if not top:
            continue

        delta = top[0] - (second[0] if second else 0.0)
        cmix = mix_number(c.get("client_name", ""))
        top_src = top[3]

        # Strict safe rules for 2nd pass:
        # 0) exact normalized name + exact normalized address
        # 1) exact normalized name + clear gap
        # 2) same Mix Markt number + clear gap
        # 3) same Mix Markt number + almost exact address
        should_apply = False
        reason = ""
        top2_src = second[3] if second else None
        top2_mix = top2_src.get("mix") if top2_src else ""
        local_name_norm = norm(c.get("client_name", ""))
        local_addr_norm = norm(f"{c.get('address', '')} {c.get('plz', '')} {c.get('city', '')}")
        top_name_norm = top_src.get("n_name", "")
        top_addr_norm = top_src.get("n_addr", "")

        if top_name_norm == local_name_norm and top_addr_norm == local_addr_norm:
            should_apply = True
            reason = "name_addr_exact"
        elif top[1] >= 0.97 and top[0] >= 0.82 and delta >= 0.06:
            should_apply = True
            reason = "name_exact"
        elif cmix and top_src.get("mix") == cmix and top[0] >= 0.75 and delta >= 0.15:
            should_apply = True
            reason = "mix_number_strong"
        elif cmix and top_src.get("mix") == cmix and top[2] >= 0.95 and delta >= 0.12:
            should_apply = True
            reason = "mix_number_address_exact"
        elif (
            cmix
            and top_src.get("mix") == cmix
            and top[0] >= 0.75
            and top[1] >= 0.70
            and delta >= 0.05
            and top2_mix
            and top2_mix != cmix
        ):
            should_apply = True
            reason = "mix_number_unique_vs_top2"

        if should_apply:
            auto_updates.append((top_src["email"], c["client_id"], reason, top[0]))

        review_rows.append(
            {
                "client_id": c.get("client_id", ""),
                "client_name": c.get("client_name", ""),
                "local_address": f"{c.get('address', '')}, {c.get('plz', '')} {c.get('city', '')}".strip(", "),
                "auto_applied": "yes" if should_apply else "no",
                "auto_reason": reason,
                "top1_score": f"{top[0]:.4f}",
                "top1_name_score": f"{top[1]:.4f}",
                "top1_addr_score": f"{top[2]:.4f}",
                "top1_name": top[3].get("name", ""),
                "top1_email": top[3].get("email", ""),
                "top1_id": top[3].get("id", ""),
                "top2_score": f"{second[0]:.4f}" if second else "",
                "top2_name": second[3].get("name", "") if second else "",
                "top2_email": second[3].get("email", "") if second else "",
                "top2_id": second[3].get("id", "") if second else "",
                "top3_score": f"{third[0]:.4f}" if third else "",
                "top3_name": third[3].get("name", "") if third else "",
                "top3_email": third[3].get("email", "") if third else "",
                "top3_id": third[3].get("id", "") if third else "",
            }
        )

    if args.apply and auto_updates:
        conn = sqlite3.connect(args.db)
        conn.executemany(
            "UPDATE client_routes SET email = ?, updated_at = ? WHERE client_id = ?",
            [(email, datetime.now().isoformat(), client_id) for email, client_id, _reason, _score in auto_updates],
        )
        conn.commit()
        conn.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = OUT_DIR / f"email_refine_report_{ts}.csv"
    with open(report, "w", encoding="utf-8", newline="") as f:
        cols = [
            "client_id", "client_name", "local_address",
            "auto_applied", "auto_reason",
            "top1_score", "top1_name_score", "top1_addr_score", "top1_name", "top1_email", "top1_id",
            "top2_score", "top2_name", "top2_email", "top2_id",
            "top3_score", "top3_name", "top3_email", "top3_id",
        ]
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";")
        w.writeheader()
        w.writerows(review_rows)

    print(f"Clients without email before pass: {len(clients)}")
    print(f"Auto-safe updates found: {len(auto_updates)}")
    print(f"Applied: {'yes' if args.apply else 'no'}")
    print(f"Report: {report}")
    if auto_updates:
        print("Applied candidates:")
        for email, client_id, reason, score in auto_updates:
            print(f"  {client_id}: {email} ({reason}, score={score:.4f})")


if __name__ == "__main__":
    main()
