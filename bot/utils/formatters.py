"""
formatters.py — Message formatting, currency formatting, and HTML escaping helpers.
"""
from __future__ import annotations

import html
from typing import Optional


def escape_html(text: Optional[str]) -> str:
    """Escape text for safe inclusion in ParseMode.HTML messages."""
    if not text:
        return ""
    return html.escape(str(text))


def format_currency(amount: float) -> str:
    """Format a monetary amount in Indian Rupees (₹)."""
    return f"₹{amount:,.2f}"


def format_user_mention(user_id: int, first_name: str, username: Optional[str] = None) -> str:
    """Create a safe HTML-formatted user mention."""
    safe_name = escape_html(first_name)
    if username:
        return f'<a href="tg://user?id={user_id}">{safe_name}</a> (@{escape_html(username)})'
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'


def format_transaction(tx: dict) -> str:
    """Format a single transaction ledger dictionary entry for presentation."""
    tx_type = tx.get("type", "unknown")
    amount = tx.get("amount", 0.0)
    desc = tx.get("description", "")
    timestamp = tx.get("timestamp", "")
    
    # Parse timestamp date part
    date_part = ""
    if timestamp:
        try:
            date_part = timestamp.split("T")[0]
        except Exception:
            pass
            
    prefix = "+" if amount >= 0 else ""
    formatted_amount = f"{prefix}{format_currency(amount)}"
    
    # Beautify types
    type_display = tx_type.replace("_", " ").title()
    
    msg = f"📅 <b>{date_part}</b> | <b>{type_display}</b>: <code>{formatted_amount}</code>"
    if desc:
        msg += f"\n└ <i>{escape_html(desc)}</i>"
    return msg
