"""Spot trading API routes"""
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
import io
from typing import Optional
import sys
from pathlib import Path
import jwt
import stripe
import logging

# Add backend/app to path for imports
backend_app_path = Path(__file__).resolve().parent.parent / "app"
if str(backend_app_path) not in sys.path:
    sys.path.insert(0, str(backend_app_path))

from app.core.dependencies import SpotTradingServiceDep
from app.core.config import settings
from spot_trade.schemas import (
    SpotTradePriceResponse,
    BuyOrderRequest,
    SellOrderRequest,
    TradeResponse,
    BalanceResponse,
    DepositCheckoutRequest,
    DepositCheckoutResponse,
    DepositConfirmRequest,
    WithdrawRequest,
    WalletTransactionItem,
    WalletTransactionsResponse,
    WithdrawApprovalRequest,
    TradeHistoryResponse,
    OpenOrdersResponse
)
from spot_trade.models import (
    get_user_trades,
    get_open_orders,
    get_all_trades,
    mark_trade_admin_seen,
    get_admin_income_summary,
)

router = APIRouter()
stripe.api_key = settings.stripe_secret_key
logger = logging.getLogger(__name__)


def ensure_stripe_account_profile() -> None:
    """Best-effort Stripe account profile bootstrap for Checkout readiness."""
    try:
        # Stripe does not allow updating account profile with test keys.
        if settings.stripe_secret_key and settings.stripe_secret_key.startswith("sk_test_"):
            return
        account = stripe.Account.retrieve()
        business_profile = getattr(account, "business_profile", None) or {}
        settings_obj = getattr(account, "settings", None) or {}
        dashboard_settings = settings_obj.get("dashboard", {}) if isinstance(settings_obj, dict) else {}
        has_business_name = bool((business_profile.get("name") if isinstance(business_profile, dict) else None))
        has_display_name = bool(dashboard_settings.get("display_name")) if isinstance(dashboard_settings, dict) else False

        if not has_business_name and not has_display_name:
            # Set minimum branding details required by Checkout for some accounts.
            stripe.Account.modify(
                account.id,
                business_profile={"name": "KGF Gold TradeX"},
                settings={"dashboard": {"display_name": "KGF Gold TradeX"}},
            )
    except Exception as e:
        # Non-fatal: Stripe may reject account updates depending on account type/permissions.
        logger.warning("Unable to auto-configure Stripe account profile: %s", str(e))


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """Decode JWT from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("userId")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return {"user_id": str(user_id), "role": payload.get("role", "USER")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "SUPER_ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_registered_user(user: dict = Depends(get_current_user)) -> dict:
    """Allow trading only for authenticated registered users."""
    user_id = str(user.get("user_id", "")).strip()
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    # Trading is available to normal registered users; keep admin support for ops/testing.
    allowed_roles = {"USER", "SUPER_ADMIN"}
    role = str(user.get("role", "USER")).upper()
    if role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only registered users can buy or sell gold",
        )
    return user


@router.get("/price", response_model=SpotTradePriceResponse)
async def get_current_price(
    spot_trading_service: SpotTradingServiceDep
):
    """Get current gold price in LKR with spread"""
    try:
        price_data = spot_trading_service.get_current_price()
        return SpotTradePriceResponse(**price_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get current price: {str(e)}"
        )


@router.post("/buy", response_model=TradeResponse)
async def place_buy_order(
    request: BuyOrderRequest,
    spot_trading_service: SpotTradingServiceDep,
    user: dict = Depends(require_registered_user)
):
    """Place a BUY market order"""
    try:
        result = spot_trading_service.place_buy_order(
            user_id=user["user_id"],
            quantity=request.quantity
        )
        return TradeResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to place BUY order: {str(e)}"
        )


@router.post("/sell", response_model=TradeResponse)
async def place_sell_order(
    request: SellOrderRequest,
    spot_trading_service: SpotTradingServiceDep,
    user: dict = Depends(require_registered_user)
):
    """Place a SELL market order"""
    try:
        result = spot_trading_service.place_sell_order(
            user_id=user["user_id"],
            quantity=request.quantity
        )
        return TradeResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to place SELL order: {str(e)}"
        )


@router.get("/balance", response_model=BalanceResponse)
async def get_user_balance(
    spot_trading_service: SpotTradingServiceDep,
    user: dict = Depends(get_current_user)
):
    """Get user balance"""
    try:
        balance = spot_trading_service.get_user_balance(user_id=user["user_id"])
        return BalanceResponse(**balance)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get balance: {str(e)}"
        )


@router.post("/deposit", response_model=DepositCheckoutResponse)
async def create_deposit_checkout(
    request_data: DepositCheckoutRequest,
    spot_trading_service: SpotTradingServiceDep,
    user: dict = Depends(get_current_user)
):
    """Create Stripe checkout for deposit"""
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stripe is not configured")
    try:
        ensure_stripe_account_profile()
        amount = float(request_data.amount)
        if amount < 5000:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Minimum deposit amount is LKR 5,000")
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "lkr",
                    "product_data": {"name": "KGF Wallet Deposit"},
                    "unit_amount": int(round(amount * 100)),
                },
                "quantity": 1,
            }],
            success_url=f"{settings.frontend_base_url}/trade?deposit=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.frontend_base_url}/trade?deposit=cancelled",
            metadata={"user_id": user["user_id"], "amount_lkr": f"{amount:.2f}"},
        )
        tx = spot_trading_service.create_deposit_checkout(user["user_id"], amount, session.id)
        return DepositCheckoutResponse(
            checkout_url=session.url,
            session_id=session.id,
            transaction_id=tx["transaction_id"],
            status=tx["status"]
        )
    except HTTPException:
        raise
    except stripe.error.InvalidRequestError as e:
        message = str(e)
        if "must set an account or business name" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stripe account setup incomplete. Go to https://dashboard.stripe.com/account and set account/business name, then retry deposit."
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stripe request failed: {message}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to initiate deposit: {str(e)}")


@router.post("/deposit/confirm", response_model=WalletTransactionItem)
async def confirm_deposit(
    request_data: DepositConfirmRequest,
    spot_trading_service: SpotTradingServiceDep,
    user: dict = Depends(get_current_user)
):
    """Confirm checkout session and credit user's wallet immediately."""
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stripe is not configured")
    try:
        session = stripe.checkout.Session.retrieve(request_data.session_id)
        payment_status = getattr(session, "payment_status", "") or ""
        tx = spot_trading_service.confirm_deposit_for_user(
            user_id=user["user_id"],
            stripe_session_id=request_data.session_id,
            payment_status=payment_status,
        )
        return WalletTransactionItem(**tx)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except stripe.error.InvalidRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Stripe session validation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to confirm deposit: {str(e)}")


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook endpoint to complete deposit"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        if settings.stripe_webhook_secret:
            event = stripe.Webhook.construct_event(payload=payload, sig_header=sig_header, secret=settings.stripe_webhook_secret)
        else:
            event = stripe.Event.construct_from(await request.json(), stripe.api_key)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid webhook payload: {str(e)}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session.get("id")
        if session_id:
            try:
                # Resolve service from app state if available
                service = request.app.state.__dict__.get("spot_trading_service")
                if service is None:
                    from app.core.dependencies import _spot_trading_service  # type: ignore
                    service = _spot_trading_service
                if service:
                    service.complete_deposit_by_stripe_session(session_id)
            except Exception:
                # Keep webhook idempotent/acknowledged to avoid repeated failures
                pass
    return JSONResponse({"received": True})


@router.post("/withdraw", response_model=WalletTransactionItem)
async def request_withdraw(
    request_data: WithdrawRequest,
    spot_trading_service: SpotTradingServiceDep,
    user: dict = Depends(get_current_user)
):
    """Create pending withdrawal request and reserve user balance immediately"""
    try:
        tx = spot_trading_service.request_withdrawal(
            user_id=user["user_id"],
            amount=float(request_data.amount),
            bank_name=request_data.bank_name,
            bank_account_number=request_data.bank_account_number,
            bank_account_name=request_data.bank_account_name,
        )
        return WalletTransactionItem(**tx)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to request withdrawal: {str(e)}")


@router.get("/history", response_model=TradeHistoryResponse)
async def get_trade_history(
    limit: int = 100,
    offset: int = 0,
    user: dict = Depends(get_current_user)
):
    """Get user trade history"""
    try:
        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit must be between 1 and 1000"
            )
        if offset < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Offset must be >= 0"
            )
        
        trades = get_user_trades(user_id=user["user_id"], limit=limit, offset=offset)
        
        from .schemas import TradeHistoryItem
        trade_items = [TradeHistoryItem(**trade) for trade in trades]
        
        return TradeHistoryResponse(
            trades=trade_items,
            total=len(trade_items),
            limit=limit,
            offset=offset
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trade history: {str(e)}"
        )


@router.get("/orders", response_model=OpenOrdersResponse)
async def get_open_orders_endpoint(
    user: dict = Depends(get_current_user)
):
    """Get user's open orders"""
    try:
        orders = get_open_orders(user_id=user["user_id"])
        
        from .schemas import OpenOrderItem
        order_items = [OpenOrderItem(**order) for order in orders]
        
        return OpenOrdersResponse(
            orders=order_items,
            total=len(order_items)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get open orders: {str(e)}"
        )


@router.get("/wallet-transactions", response_model=WalletTransactionsResponse)
async def get_wallet_transactions_for_user(
    spot_trading_service: SpotTradingServiceDep,
    limit: int = 100,
    offset: int = 0,
    user: dict = Depends(get_current_user)
):
    """Get wallet transactions for logged-in user"""
    transactions = spot_trading_service.get_wallet_transactions_for_user(user["user_id"], limit=limit, offset=offset)
    return WalletTransactionsResponse(
        transactions=[WalletTransactionItem(**tx) for tx in transactions],
        total=len(transactions),
        limit=limit,
        offset=offset
    )


@router.get("/admin/wallet-transactions", response_model=WalletTransactionsResponse)
async def get_wallet_transactions_for_admin(
    spot_trading_service: SpotTradingServiceDep,
    status_filter: Optional[str] = None,
    transaction_type: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    _admin: dict = Depends(require_admin)
):
    """Admin listing of wallet transactions"""
    transactions = spot_trading_service.get_wallet_transactions_for_admin(
        status=status_filter,
        transaction_type=transaction_type,
        limit=limit,
        offset=offset,
    )
    return WalletTransactionsResponse(
        transactions=[WalletTransactionItem(**tx) for tx in transactions],
        total=len(transactions),
        limit=limit,
        offset=offset
    )


@router.post("/admin/withdrawals/{transaction_id}/decision", response_model=WalletTransactionItem)
async def approve_or_reject_withdrawal(
    transaction_id: int,
    request_data: WithdrawApprovalRequest,
    spot_trading_service: SpotTradingServiceDep,
    admin: dict = Depends(require_admin)
):
    """Approve or reject pending withdrawal"""
    try:
        tx = spot_trading_service.approve_withdrawal(
            transaction_id=transaction_id,
            admin_user_id=admin["user_id"],
            approve=request_data.approve,
            notes=request_data.notes,
        )
        return WalletTransactionItem(**tx)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process withdrawal decision: {str(e)}")


@router.get("/admin/spot-trades")
async def get_spot_trades_for_admin(
    limit: int = 200,
    offset: int = 0,
    _admin: dict = Depends(require_admin)
):
    """Super-admin listing of all BUY/SELL spot trades with review (seen) status."""
    from .schemas import AdminSpotTradeItem, AdminSpotTradeListResponse

    trades = get_all_trades(limit=limit, offset=offset)
    items = [AdminSpotTradeItem(**trade) for trade in trades]
    return AdminSpotTradeListResponse(trades=items, total=len(items), limit=limit, offset=offset)


@router.post("/admin/spot-trades/{trade_id}/seen")
async def mark_spot_trade_seen(
    trade_id: int,
    admin: dict = Depends(require_admin),
):
    """Mark a gold buy/sell trade as seen by the current super admin."""
    from .schemas import AdminSpotTradeItem

    trade = mark_trade_admin_seen(trade_id, admin["user_id"])
    if not trade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    return AdminSpotTradeItem(**trade)


@router.get("/admin/income/summary")
async def get_income_summary_for_admin(_admin: dict = Depends(require_admin)):
    """Platform revenue (fees) summary for the super-admin dashboard."""
    from .schemas import AdminIncomeSummary

    summary = get_admin_income_summary()
    return AdminIncomeSummary(**summary)


@router.get("/admin/backup")
async def download_admin_backup(admin: dict = Depends(require_admin)):
    """Full spot-trading database export (ZIP + manifest) for super admins."""
    from datetime import datetime, timezone
    from .backup import build_spot_backup_zip

    exported_by = str(admin.get("user_id", "super_admin"))
    zip_bytes = build_spot_backup_zip(exported_by=exported_by)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"kgf-spot-trading-backup_{stamp}.zip"

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )

