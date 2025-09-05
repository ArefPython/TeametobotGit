from datetime import datetime
from typing import Dict, Any
from ..utils.time import now_local

POINT_VALUE = 50_000  # each point = 100,000 Toman

def update_balance(user: Dict[str, Any]) -> None:
    """Recalculate balance from points (if not already tracked)."""
    points = int(user.get("points", 0))
    user["balance"] = points * POINT_VALUE

def get_balance(user: Dict[str, Any]) -> int:
    """Return user's current balance in Tomans."""
    update_balance(user)
    return int(user.get("balance", 0))

def request_withdrawal(user: Dict[str, Any], amount: int) -> Dict[str, Any]:
    """
    Request withdrawal of a given amount (Tomans).
    Adds record to withdrawals and reduces balance (pending admin approval).
    """
    balance = get_balance(user)
    if amount > balance:
        raise ValueError("Insufficient balance")
    points_needed = amount // POINT_VALUE
    current_points = int(user.get("points", 0))
    if points_needed > current_points:
        raise ValueError("Insufficient points")
    
    
    user["points"] = current_points - points_needed
    update_balance(user)


    withdrawal = {
        "datetime": now_local().strftime("%Y-%m-%d %H:%M"),
        "amount": amount,
        "status": "pending"
    }
    user.setdefault("withdrawals", []).append(withdrawal)

    # temporarily deduct from balance
    user["balance"] = balance - amount
    return withdrawal
