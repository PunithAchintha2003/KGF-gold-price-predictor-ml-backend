"""Database models for spot trading"""
import logging
from datetime import datetime
from typing import Optional
from enum import Enum
import sys
from pathlib import Path

# Add backend/app to path for imports
backend_app_path = Path(__file__).resolve().parent.parent / "app"
if str(backend_app_path) not in sys.path:
    sys.path.insert(0, str(backend_app_path))

from app.core.database import get_db_connection, get_db_type
from app.core.config import settings

logger = logging.getLogger(__name__)


class OrderType(str, Enum):
    """Order type enumeration"""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Order status enumeration"""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WalletTransactionType(str, Enum):
    """Wallet transaction types"""
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"


class WalletTransactionStatus(str, Enum):
    """Wallet transaction statuses"""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


def init_spot_trade_tables():
    """Initialize spot trading database tables"""
    db_type = get_db_type()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if db_type == "postgresql":
            # PostgreSQL table creation
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_balances (
                    user_id VARCHAR(255) PRIMARY KEY,
                    lkr_balance DECIMAL(20, 2) NOT NULL DEFAULT 0.0,
                    gold_balance DECIMAL(20, 8) NOT NULL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS spot_trades (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    order_type VARCHAR(10) NOT NULL CHECK (order_type IN ('BUY', 'SELL')),
                    quantity DECIMAL(20, 8) NOT NULL CHECK (quantity > 0),
                    price DECIMAL(20, 2) NOT NULL CHECK (price > 0),
                    total_value DECIMAL(20, 2) NOT NULL CHECK (total_value > 0),
                    fee DECIMAL(20, 2) DEFAULT 0.0,
                    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'COMPLETED', 'FAILED', 'CANCELLED')),
                    admin_seen BOOLEAN NOT NULL DEFAULT FALSE,
                    admin_seen_at TIMESTAMP,
                    admin_seen_by VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES user_balances(user_id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spot_trades_user_id ON spot_trades(user_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spot_trades_created_at ON spot_trades(created_at DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spot_trades_status ON spot_trades(status)
            """)

            # Migration: Add fee column to existing spot_trades table if it doesn't exist (PostgreSQL)
            try:
                cursor.execute("""
                    ALTER TABLE spot_trades ADD COLUMN fee DECIMAL(20, 2) DEFAULT 0.0
                """)
                conn.commit()
                logger.info("✅ Added fee column to spot_trades table (PostgreSQL)")
            except Exception:
                # Column already exists or other error - continue
                conn.rollback()
                pass

            for migration_sql in (
                "ALTER TABLE spot_trades ADD COLUMN admin_seen BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE spot_trades ADD COLUMN admin_seen_at TIMESTAMP",
                "ALTER TABLE spot_trades ADD COLUMN admin_seen_by VARCHAR(255)",
            ):
                try:
                    cursor.execute(migration_sql)
                    conn.commit()
                except Exception:
                    conn.rollback()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wallet_transactions (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('DEPOSIT', 'WITHDRAWAL')),
                    amount DECIMAL(20, 2) NOT NULL CHECK (amount > 0),
                    fee DECIMAL(20, 2) DEFAULT 0.0,
                    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'COMPLETED', 'APPROVED', 'REJECTED', 'FAILED')),
                    payment_method VARCHAR(50),
                    stripe_session_id VARCHAR(255),
                    bank_name VARCHAR(255),
                    bank_account_number VARCHAR(100),
                    bank_account_name VARCHAR(255),
                    notes TEXT,
                    approved_by VARCHAR(255),
                    approved_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES user_balances(user_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user_id ON wallet_transactions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_status ON wallet_transactions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_type ON wallet_transactions(transaction_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_created_at ON wallet_transactions(created_at DESC)")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_transactions_stripe_session ON wallet_transactions(stripe_session_id)")
        else:
            # SQLite table creation
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_balances (
                    user_id TEXT PRIMARY KEY,
                    lkr_balance REAL NOT NULL DEFAULT 0.0,
                    gold_balance REAL NOT NULL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS spot_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    order_type TEXT NOT NULL CHECK (order_type IN ('BUY', 'SELL')),
                    quantity REAL NOT NULL CHECK (quantity > 0),
                    price REAL NOT NULL CHECK (price > 0),
                    total_value REAL NOT NULL CHECK (total_value > 0),
                    fee REAL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'COMPLETED', 'FAILED', 'CANCELLED')),
                    admin_seen INTEGER NOT NULL DEFAULT 0,
                    admin_seen_at TIMESTAMP,
                    admin_seen_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES user_balances(user_id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spot_trades_user_id ON spot_trades(user_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spot_trades_created_at ON spot_trades(created_at DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_spot_trades_status ON spot_trades(status)
            """)

            # Migration: Add fee column to existing spot_trades table if it doesn't exist (SQLite)
            try:
                cursor.execute("""
                    ALTER TABLE spot_trades ADD COLUMN fee REAL DEFAULT 0.0
                """)
                conn.commit()
                logger.info("✅ Added fee column to spot_trades table (SQLite)")
            except Exception:
                # Column already exists or other error - continue
                conn.rollback()
                pass

            for migration_sql in (
                "ALTER TABLE spot_trades ADD COLUMN admin_seen INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE spot_trades ADD COLUMN admin_seen_at TIMESTAMP",
                "ALTER TABLE spot_trades ADD COLUMN admin_seen_by TEXT",
            ):
                try:
                    cursor.execute(migration_sql)
                    conn.commit()
                except Exception:
                    conn.rollback()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wallet_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('DEPOSIT', 'WITHDRAWAL')),
                    amount REAL NOT NULL CHECK (amount > 0),
                    fee REAL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'COMPLETED', 'APPROVED', 'REJECTED', 'FAILED')),
                    payment_method TEXT,
                    stripe_session_id TEXT,
                    bank_name TEXT,
                    bank_account_number TEXT,
                    bank_account_name TEXT,
                    notes TEXT,
                    approved_by TEXT,
                    approved_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES user_balances(user_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user_id ON wallet_transactions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_status ON wallet_transactions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_type ON wallet_transactions(transaction_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_created_at ON wallet_transactions(created_at DESC)")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_transactions_stripe_session ON wallet_transactions(stripe_session_id)")
        
        conn.commit()
        logger.debug("✅ Spot trading tables initialized")


def get_or_create_user_balance(user_id: str) -> dict:
    """Get or create user balance record"""
    db_type = get_db_type()
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Try to get existing balance
            if db_type == "postgresql":
                cursor.execute(
                    "SELECT user_id, lkr_balance, gold_balance, created_at, updated_at FROM user_balances WHERE user_id = %s",
                    (user_id,)
                )
            else:
                cursor.execute(
                    "SELECT user_id, lkr_balance, gold_balance, created_at, updated_at FROM user_balances WHERE user_id = ?",
                    (user_id,)
                )
            row = cursor.fetchone()
            
            if row:
                return {
                    "user_id": row[0],
                    "lkr_balance": float(row[1]),
                    "gold_balance": float(row[2]),
                    "created_at": row[3],
                    "updated_at": row[4]
                }
            
            # Create new balance record with default values
            now = datetime.now()
            
            if db_type == "postgresql":
                cursor.execute(
                    """INSERT INTO user_balances (user_id, lkr_balance, gold_balance, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (user_id) DO NOTHING
                       RETURNING user_id, lkr_balance, gold_balance, created_at, updated_at""",
                    (user_id, 0.0, 0.0, now, now)
                )
                row = cursor.fetchone()
                if row:
                    conn.commit()
                    return {
                        "user_id": row[0],
                        "lkr_balance": float(row[1]),
                        "gold_balance": float(row[2]),
                        "created_at": row[3],
                        "updated_at": row[4]
                    }
            else:
                cursor.execute(
                    """INSERT OR IGNORE INTO user_balances (user_id, lkr_balance, gold_balance, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, 0.0, 0.0, now, now)
                )
                conn.commit()
                
                # Fetch the created record
                cursor.execute(
                    "SELECT user_id, lkr_balance, gold_balance, created_at, updated_at FROM user_balances WHERE user_id = ?",
                    (user_id,)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "user_id": row[0],
                        "lkr_balance": float(row[1]),
                        "gold_balance": float(row[2]),
                        "created_at": row[3],
                        "updated_at": row[4]
                    }
            
            conn.commit()
            return {
                "user_id": user_id,
                "lkr_balance": 0.0,
                "gold_balance": 0.0,
                "created_at": now,
                "updated_at": now
            }
    except Exception as e:
        logger.error(f"Error in get_or_create_user_balance: {e}", exc_info=True)
        # Return default balance on error
        now = datetime.now()
        return {
            "user_id": user_id,
            "lkr_balance": 0.0,
            "gold_balance": 0.0,
            "created_at": now,
            "updated_at": now
        }


def update_user_balance(user_id: str, lkr_balance: Optional[float] = None, gold_balance: Optional[float] = None) -> bool:
    """Update user balance"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        db_type = get_db_type()
        now = datetime.now()
        
        updates = []
        params = []
        
        if lkr_balance is not None:
            updates.append("lkr_balance = ?" if db_type != "postgresql" else "lkr_balance = %s")
            params.append(lkr_balance)
        
        if gold_balance is not None:
            updates.append("gold_balance = ?" if db_type != "postgresql" else "gold_balance = %s")
            params.append(gold_balance)
        
        if not updates:
            return False
        
        updates.append("updated_at = ?" if db_type != "postgresql" else "updated_at = %s")
        params.append(now)
        params.append(user_id)
        
        if db_type == "postgresql":
            query = f"UPDATE user_balances SET {', '.join(updates)} WHERE user_id = %s"
        else:
            query = f"UPDATE user_balances SET {', '.join(updates)} WHERE user_id = ?"
        
        cursor.execute(query, params)
        conn.commit()
        return cursor.rowcount > 0


def create_trade(user_id: str, order_type: str, quantity: float, price: float, total_value: float, fee: float = 0.0, status: str = "PENDING") -> Optional[int]:
    """Create a new trade record"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        db_type = get_db_type()
        now = datetime.now()
        
        if db_type == "postgresql":
            cursor.execute(
                """INSERT INTO spot_trades (user_id, order_type, quantity, price, total_value, fee, status, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (user_id, order_type, quantity, price, total_value, fee, status, now, now)
            )
            row = cursor.fetchone()
            trade_id = row[0] if row else None
        else:
            cursor.execute(
                """INSERT INTO spot_trades (user_id, order_type, quantity, price, total_value, fee, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, order_type, quantity, price, total_value, fee, status, now, now)
            )
            trade_id = cursor.lastrowid
        
        conn.commit()
        return trade_id


def update_trade_status(trade_id: int, status: str) -> bool:
    """Update trade status"""
    db_type = get_db_type()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now()
        
        if db_type == "postgresql":
            cursor.execute(
                "UPDATE spot_trades SET status = %s, updated_at = %s WHERE id = %s",
                (status, now, trade_id)
            )
        else:
            cursor.execute(
                "UPDATE spot_trades SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, trade_id)
            )
        
        conn.commit()
        return cursor.rowcount > 0


def get_user_trades(user_id: str, limit: int = 100, offset: int = 0) -> list:
    """Get user's trade history (quantities converted to pawn for frontend)"""
    # Conversion: 1 troy ounce = 31.1035 / 8 = 3.8879375 pawn
    TROY_OUNCE_TO_PAWN = 31.1035 / 8.0
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        db_type = get_db_type()
        
        if db_type == "postgresql":
            cursor.execute(
                """SELECT id, user_id, order_type, quantity, price, total_value, fee, status, created_at, updated_at
                   FROM spot_trades
                   WHERE user_id = %s
                   ORDER BY created_at DESC
                   LIMIT %s OFFSET %s""",
                (user_id, limit, offset)
            )
        else:
            cursor.execute(
                """SELECT id, user_id, order_type, quantity, price, total_value, fee, status, created_at, updated_at
                   FROM spot_trades
                   WHERE user_id = ?
                   ORDER BY created_at DESC
                   LIMIT ? OFFSET ?""",
                (user_id, limit, offset)
            )
        
        rows = cursor.fetchall()
        trades = []
        
        for row in rows:
            # Convert quantity from troy ounces to pawn
            quantity_troy_ounces = float(row[3])
            quantity_pawn = quantity_troy_ounces * TROY_OUNCE_TO_PAWN
            
            trades.append({
                "id": row[0],
                "user_id": row[1],
                "order_type": row[2],
                "quantity": quantity_pawn,  # Return in pawn
                "price": float(row[4]),  # Price is already in LKR per pawn
                "total_value": float(row[5]),
                "fee": float(row[6]) if row[6] is not None else 0.0,
                "status": row[7],
                "created_at": row[8].isoformat() if hasattr(row[8], 'isoformat') else str(row[8]),
                "updated_at": row[9].isoformat() if hasattr(row[9], 'isoformat') else str(row[9])
            })
        
        return trades


def get_open_orders(user_id: str) -> list:
    """Get user's open (pending) orders (quantities converted to pawn for frontend)"""
    db_type = get_db_type()
    # Conversion: 1 troy ounce = 31.1035 / 8 = 3.8879375 pawn
    TROY_OUNCE_TO_PAWN = 31.1035 / 8.0
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if db_type == "postgresql":
            cursor.execute(
                """SELECT id, user_id, order_type, quantity, price, total_value, fee, status, created_at, updated_at
                   FROM spot_trades
                   WHERE user_id = %s AND status = 'PENDING'
                   ORDER BY created_at DESC""",
                (user_id,)
            )
        else:
            cursor.execute(
                """SELECT id, user_id, order_type, quantity, price, total_value, fee, status, created_at, updated_at
                   FROM spot_trades
                   WHERE user_id = ? AND status = 'PENDING'
                   ORDER BY created_at DESC""",
                (user_id,)
            )
        
        rows = cursor.fetchall()
        orders = []
        
        for row in rows:
            # Convert quantity from troy ounces to pawn
            quantity_troy_ounces = float(row[3])
            quantity_pawn = quantity_troy_ounces * TROY_OUNCE_TO_PAWN
            
            orders.append({
                "id": row[0],
                "user_id": row[1],
                "order_type": row[2],
                "quantity": quantity_pawn,  # Return in pawn
                "price": float(row[4]),  # Price is already in LKR per pawn
                "total_value": float(row[5]),
                "fee": float(row[6]) if row[6] is not None else 0.0,
                "status": row[7],
                "created_at": row[8].isoformat() if hasattr(row[8], 'isoformat') else str(row[8]),
                "updated_at": row[9].isoformat() if hasattr(row[9], 'isoformat') else str(row[9])
            })
        
        return orders


def _parse_admin_seen(value) -> bool:
    """Coerce admin_seen column values from any supported backend to a Python bool."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(value)


def _format_trade_row_for_admin(row) -> dict:
    """Map admin spot_trades SELECT row to API dict (quantities in pawn).

    Expected SELECT column order:
        0:id, 1:user_id, 2:order_type, 3:quantity, 4:price, 5:total_value,
        6:fee, 7:status, 8:created_at, 9:updated_at,
        10:admin_seen, 11:admin_seen_at, 12:admin_seen_by
    """
    TROY_OUNCE_TO_PAWN = 31.1035 / 8.0
    admin_seen_at = row[11]
    return {
        "id": row[0],
        "user_id": row[1],
        "order_type": row[2],
        "quantity": float(row[3]) * TROY_OUNCE_TO_PAWN,
        "price": float(row[4]),
        "total_value": float(row[5]),
        "fee": float(row[6]) if row[6] is not None else 0.0,
        "status": row[7],
        "created_at": row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8]),
        "updated_at": row[9].isoformat() if hasattr(row[9], "isoformat") else str(row[9]),
        "admin_seen": _parse_admin_seen(row[10]),
        "admin_seen_at": (
            admin_seen_at.isoformat()
            if admin_seen_at is not None and hasattr(admin_seen_at, "isoformat")
            else (str(admin_seen_at) if admin_seen_at is not None else None)
        ),
        "admin_seen_by": row[12],
    }


def get_all_trades(limit: int = 200, offset: int = 0) -> list:
    """Get all spot trades for super-admin review (includes seen status)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        db_type = get_db_type()
        if db_type == "postgresql":
            cursor.execute(
                """SELECT id, user_id, order_type, quantity, price, total_value, fee, status,
                          created_at, updated_at, admin_seen, admin_seen_at, admin_seen_by
                   FROM spot_trades
                   ORDER BY created_at DESC
                   LIMIT %s OFFSET %s""",
                (limit, offset),
            )
        else:
            cursor.execute(
                """SELECT id, user_id, order_type, quantity, price, total_value, fee, status,
                          created_at, updated_at, admin_seen, admin_seen_at, admin_seen_by
                   FROM spot_trades
                   ORDER BY created_at DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            )
        rows = cursor.fetchall()
        return [_format_trade_row_for_admin(row) for row in rows]


def get_admin_income_summary() -> dict:
    """Aggregate platform revenue (fees) from completed trades and wallet transactions.

    Returns totals in LKR for: all-time, today, and current month. Also returns
    a breakdown by source (spot_trades vs wallet_transactions) and the most
    recent revenue timestamp.

    Only revenue-earning rows are counted:
      - spot_trades.status = 'COMPLETED'
      - wallet_transactions.status IN ('COMPLETED', 'APPROVED')
    """
    db_type = get_db_type()

    if db_type == "postgresql":
        today_predicate = "created_at >= DATE_TRUNC('day', CURRENT_TIMESTAMP)"
        month_predicate = "created_at >= DATE_TRUNC('month', CURRENT_TIMESTAMP)"
    else:
        today_predicate = "date(created_at) = date('now')"
        month_predicate = "strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"

    def _scalar(cursor) -> float:
        row = cursor.fetchone()
        if not row or row[0] is None:
            return 0.0
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return 0.0

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Spot trade fees (BUY/SELL revenue)
        cursor.execute(
            "SELECT COALESCE(SUM(fee), 0) FROM spot_trades WHERE status = 'COMPLETED'"
        )
        trade_total = _scalar(cursor)

        cursor.execute(
            f"SELECT COALESCE(SUM(fee), 0) FROM spot_trades "
            f"WHERE status = 'COMPLETED' AND {today_predicate}"
        )
        trade_today = _scalar(cursor)

        cursor.execute(
            f"SELECT COALESCE(SUM(fee), 0) FROM spot_trades "
            f"WHERE status = 'COMPLETED' AND {month_predicate}"
        )
        trade_month = _scalar(cursor)

        # Wallet transaction fees (deposit/withdraw revenue)
        cursor.execute(
            "SELECT COALESCE(SUM(fee), 0) FROM wallet_transactions "
            "WHERE status IN ('COMPLETED', 'APPROVED')"
        )
        wallet_total = _scalar(cursor)

        cursor.execute(
            f"SELECT COALESCE(SUM(fee), 0) FROM wallet_transactions "
            f"WHERE status IN ('COMPLETED', 'APPROVED') AND {today_predicate}"
        )
        wallet_today = _scalar(cursor)

        cursor.execute(
            f"SELECT COALESCE(SUM(fee), 0) FROM wallet_transactions "
            f"WHERE status IN ('COMPLETED', 'APPROVED') AND {month_predicate}"
        )
        wallet_month = _scalar(cursor)

        # Most recent revenue timestamp (whichever of the two tables is fresher)
        cursor.execute(
            """
            SELECT MAX(ts) FROM (
                SELECT MAX(created_at) AS ts FROM spot_trades WHERE status = 'COMPLETED'
                UNION ALL
                SELECT MAX(created_at) AS ts FROM wallet_transactions
                WHERE status IN ('COMPLETED', 'APPROVED')
            ) AS latest
            """
        )
        latest_row = cursor.fetchone()
        latest_ts = latest_row[0] if latest_row else None
        last_revenue_at = (
            latest_ts.isoformat()
            if latest_ts is not None and hasattr(latest_ts, "isoformat")
            else (str(latest_ts) if latest_ts is not None else None)
        )

    return {
        "currency": "LKR",
        "total": round(trade_total + wallet_total, 2),
        "today": round(trade_today + wallet_today, 2),
        "this_month": round(trade_month + wallet_month, 2),
        "trade_fees": {
            "total": round(trade_total, 2),
            "today": round(trade_today, 2),
            "this_month": round(trade_month, 2),
        },
        "wallet_fees": {
            "total": round(wallet_total, 2),
            "today": round(wallet_today, 2),
            "this_month": round(wallet_month, 2),
        },
        "last_revenue_at": last_revenue_at,
    }


def mark_trade_admin_seen(trade_id: int, admin_user_id: str) -> Optional[dict]:
    """Mark a spot trade as reviewed by super admin."""
    now = datetime.utcnow()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        db_type = get_db_type()
        if db_type == "postgresql":
            cursor.execute(
                """UPDATE spot_trades
                   SET admin_seen = TRUE, admin_seen_at = %s, admin_seen_by = %s, updated_at = %s
                   WHERE id = %s""",
                (now, admin_user_id, now, trade_id),
            )
        else:
            cursor.execute(
                """UPDATE spot_trades
                   SET admin_seen = 1, admin_seen_at = ?, admin_seen_by = ?, updated_at = ?
                   WHERE id = ?""",
                (now, admin_user_id, now, trade_id),
            )
        if cursor.rowcount == 0:
            return None

        conn.commit()

        if db_type == "postgresql":
            cursor.execute(
                """SELECT id, user_id, order_type, quantity, price, total_value, fee, status,
                          created_at, updated_at, admin_seen, admin_seen_at, admin_seen_by
                   FROM spot_trades WHERE id = %s""",
                (trade_id,),
            )
        else:
            cursor.execute(
                """SELECT id, user_id, order_type, quantity, price, total_value, fee, status,
                          created_at, updated_at, admin_seen, admin_seen_at, admin_seen_by
                   FROM spot_trades WHERE id = ?""",
                (trade_id,),
            )
        row = cursor.fetchone()
        if not row:
            return None
        return _format_trade_row_for_admin(row)


def create_wallet_transaction(
    user_id: str,
    transaction_type: str,
    amount: float,
    status: str = WalletTransactionStatus.PENDING,
    payment_method: Optional[str] = None,
    stripe_session_id: Optional[str] = None,
    bank_name: Optional[str] = None,
    bank_account_number: Optional[str] = None,
    bank_account_name: Optional[str] = None,
    notes: Optional[str] = None,
    fee: float = 0.0
) -> Optional[int]:
    """Create wallet transaction record"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        db_type = get_db_type()
        now = datetime.now()
        if db_type == "postgresql":
            cursor.execute(
                """INSERT INTO wallet_transactions
                   (user_id, transaction_type, amount, fee, status, payment_method, stripe_session_id, bank_name, bank_account_number, bank_account_name, notes, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (user_id, transaction_type, amount, fee, status, payment_method, stripe_session_id, bank_name, bank_account_number, bank_account_name, notes, now, now)
            )
            row = cursor.fetchone()
            tx_id = row[0] if row else None
        else:
            cursor.execute(
                """INSERT INTO wallet_transactions
                   (user_id, transaction_type, amount, fee, status, payment_method, stripe_session_id, bank_name, bank_account_number, bank_account_name, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, transaction_type, amount, fee, status, payment_method, stripe_session_id, bank_name, bank_account_number, bank_account_name, notes, now, now)
            )
            tx_id = cursor.lastrowid
        conn.commit()
        return tx_id


def get_wallet_transaction_by_id(transaction_id: int) -> Optional[dict]:
    """Get wallet transaction by id"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        db_type = get_db_type()
        placeholder = "%s" if db_type == "postgresql" else "?"
        cursor.execute(
            f"""SELECT id, user_id, transaction_type, amount, fee, status, payment_method, stripe_session_id,
                       bank_name, bank_account_number, bank_account_name, notes, approved_by, approved_at, created_at, updated_at
                FROM wallet_transactions WHERE id = {placeholder}""",
            (transaction_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return _wallet_row_to_dict(row)


def get_wallet_transaction_by_stripe_session(stripe_session_id: str) -> Optional[dict]:
    """Get wallet transaction by stripe session id"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        db_type = get_db_type()
        placeholder = "%s" if db_type == "postgresql" else "?"
        cursor.execute(
            f"""SELECT id, user_id, transaction_type, amount, fee, status, payment_method, stripe_session_id,
                       bank_name, bank_account_number, bank_account_name, notes, approved_by, approved_at, created_at, updated_at
                FROM wallet_transactions WHERE stripe_session_id = {placeholder}""",
            (stripe_session_id,)
        )
        row = cursor.fetchone()
        return _wallet_row_to_dict(row) if row else None


def update_wallet_transaction_status(transaction_id: int, status: str, approved_by: Optional[str] = None, notes: Optional[str] = None) -> bool:
    """Update wallet transaction status"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        db_type = get_db_type()
        now = datetime.now()
        if db_type == "postgresql":
            cursor.execute(
                """UPDATE wallet_transactions
                   SET status = %s, approved_by = %s, approved_at = %s, notes = COALESCE(%s, notes), updated_at = %s
                   WHERE id = %s""",
                (status, approved_by, now if approved_by else None, notes, now, transaction_id)
            )
        else:
            cursor.execute(
                """UPDATE wallet_transactions
                   SET status = ?, approved_by = ?, approved_at = ?, notes = COALESCE(?, notes), updated_at = ?
                   WHERE id = ?""",
                (status, approved_by, now if approved_by else None, notes, now, transaction_id)
            )
        conn.commit()
        return cursor.rowcount > 0


def get_wallet_transactions(user_id: Optional[str] = None, status: Optional[str] = None, transaction_type: Optional[str] = None, limit: int = 100, offset: int = 0) -> list:
    """Get wallet transactions with filters"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        db_type = get_db_type()
        placeholder = "%s" if db_type == "postgresql" else "?"
        where = []
        params = []
        if user_id:
            where.append(f"user_id = {placeholder}")
            params.append(user_id)
        if status:
            where.append(f"status = {placeholder}")
            params.append(status)
        if transaction_type:
            where.append(f"transaction_type = {placeholder}")
            params.append(transaction_type)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        query = f"""SELECT id, user_id, transaction_type, amount, fee, status, payment_method, stripe_session_id,
                           bank_name, bank_account_number, bank_account_name, notes, approved_by, approved_at, created_at, updated_at
                    FROM wallet_transactions
                    {where_sql}
                    ORDER BY created_at DESC
                    LIMIT {placeholder} OFFSET {placeholder}"""
        params.extend([limit, offset])
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        return [_wallet_row_to_dict(row) for row in rows]


def _wallet_row_to_dict(row) -> dict:
    """Convert wallet tx row to dict"""
    return {
        "id": row[0],
        "user_id": row[1],
        "transaction_type": row[2],
        "amount": float(row[3]),
        "fee": float(row[4]) if row[4] is not None else 0.0,
        "status": row[5],
        "payment_method": row[6],
        "stripe_session_id": row[7],
        "bank_name": row[8],
        "bank_account_number": row[9],
        "bank_account_name": row[10],
        "notes": row[11],
        "approved_by": row[12],
        "approved_at": row[13].isoformat() if row[13] and hasattr(row[13], 'isoformat') else (str(row[13]) if row[13] else None),
        "created_at": row[14].isoformat() if hasattr(row[14], 'isoformat') else str(row[14]),
        "updated_at": row[15].isoformat() if hasattr(row[15], 'isoformat') else str(row[15]),
    }

