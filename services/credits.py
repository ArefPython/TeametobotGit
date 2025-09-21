from typing import Dict, Any

from ..utils.time import now_local

POINT_VALUE = 50_000  # each point = 50,000 Toman


def update_balance(user: Dict[str, Any]) -> None:
    """Recalculate balance from points."""
    points = int(user.get("points", 0))
    user["balance"] = points * POINT_VALUE


def get_balance(user: Dict[str, Any]) -> int:
    """Return user's current balance in Tomans."""
    update_balance(user)
    return int(user.get("balance", 0))


def request_withdrawal(user: Dict[str, Any], amount: int) -> Dict[str, Any]:
    """Create a pending withdrawal and deduct the equivalent points."""
    if amount <= 0:
        raise ValueError("مبلغ باید عددی مثبت باشد")
    if amount % POINT_VALUE != 0:
        raise ValueError(f"مبلغ باید مضربی از {POINT_VALUE:,} تومان باشد")

    balance = get_balance(user)
    if amount > balance:
        raise ValueError("موجودی کافی نیست")

    points_needed = amount // POINT_VALUE
    current_points = int(user.get("points", 0))
    if points_needed > current_points:
        raise ValueError("امتیاز کافی نیست")

    user["points"] = current_points - points_needed
    update_balance(user)

    withdrawal = {
        "datetime": now_local().strftime("%Y-%m-%d %H:%M"),
        "amount": amount,
        "points": points_needed,
        "status": "pending",
    }
    user.setdefault("withdrawals", []).append(withdrawal)

    user["balance"] = balance - amount
    return withdrawal
