"""Super-admin full export of spot trading database tables."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from app.core.database import get_db_connection, get_db_type
from spot_trade.models import (
    get_admin_income_summary,
    get_all_trades,
    get_wallet_transactions,
)

BACKUP_FORMAT_VERSION = "1.0"
MAX_EXPORT_ROWS = 500_000


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _balance_row_to_dict(row) -> dict[str, Any]:
    return {
        "user_id": row[0],
        "lkr_balance": float(row[1]),
        "gold_balance": float(row[2]),
        "created_at": row[3].isoformat() if hasattr(row[3], "isoformat") else str(row[3]),
        "updated_at": row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4]),
    }


def export_all_user_balances() -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, lkr_balance, gold_balance, created_at, updated_at
            FROM user_balances
            ORDER BY user_id
            """
        )
        rows = cursor.fetchall()
        return [_balance_row_to_dict(row) for row in rows]


def collect_spot_backup_payload() -> dict[str, Any]:
    """Gather all spot-trading tables for backup (no secrets)."""
    user_balances = export_all_user_balances()
    spot_trades = get_all_trades(limit=MAX_EXPORT_ROWS, offset=0)
    wallet_transactions = get_wallet_transactions(
        limit=MAX_EXPORT_ROWS, offset=0
    )
    income_summary = get_admin_income_summary()

    return {
        "user_balances": user_balances,
        "spot_trades": spot_trades,
        "wallet_transactions": wallet_transactions,
        "income_summary": income_summary,
    }


def build_spot_backup_zip(*, exported_by: str) -> bytes:
    """ZIP archive with manifest, per-table JSON, and SHA-256 checksums."""
    exported_at = _iso_now()
    payload = collect_spot_backup_payload()

    files: dict[str, Any] = {
        "data/user_balances.json": payload["user_balances"],
        "data/spot_trades.json": payload["spot_trades"],
        "data/wallet_transactions.json": payload["wallet_transactions"],
        "data/income_summary.json": payload["income_summary"],
    }

    checksums: dict[str, str] = {}
    for path, content in files.items():
        checksums[path] = _sha256_text(
            json.dumps(content, indent=2, default=str, ensure_ascii=False)
        )

    manifest = {
        "backup_format_version": BACKUP_FORMAT_VERSION,
        "application": "kgf-gold-tradex",
        "scope": "spot_trading",
        "exported_at": exported_at,
        "exported_by": exported_by,
        "database": get_db_type(),
        "record_counts": {
            "user_balances": len(payload["user_balances"]),
            "spot_trades": len(payload["spot_trades"]),
            "wallet_transactions": len(payload["wallet_transactions"]),
        },
        "files": list(files.keys()) + ["manifest.json"],
        "checksums_sha256": checksums,
        "notes": "Secrets (passwords, tokens) are never included. Use for disaster recovery and audits.",
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False),
        )
        for path, content in files.items():
            zf.writestr(
                path,
                json.dumps(content, indent=2, default=str, ensure_ascii=False),
            )

    buffer.seek(0)
    return buffer.getvalue()
