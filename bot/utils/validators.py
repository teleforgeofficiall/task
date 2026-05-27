"""
validators.py — Input validation helpers for user inputs.
"""
from __future__ import annotations

import re


# UPI ID format validation: alphanumeric/dots/hyphens/underscores, at symbol, followed by bank handle
# e.g., user@paytm, user@ybl, john.doe@okaxis, 1234567890@paytm
UPI_REGEX = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")


def validate_upi_id(upi_id: str) -> bool:
    """Validate that a string matches the standard UPI ID format."""
    if not upi_id:
        return False
    return bool(UPI_REGEX.match(upi_id.strip()))


def is_valid_username(username: str) -> bool:
    """Validate a Telegram username (minimum 5 chars, alphanumeric or underscore)."""
    if not username:
        return False
    username = username.lstrip("@")
    return bool(re.match(r"^[a-zA-Z0-9_]{5,32}$", username))
