"""Parse Kenyan M-Pesa confirmation SMS / message text for reconciliation."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_RECEIPT_PATTERNS = (
    re.compile(
        r'(?:confirmation\s+code|receipt(?:\s+no\.?)?|transaction\s+id|trans(?:action)?\s*id)'
        r'\s*(?:is\s*)?[:\s]*([A-Z0-9]{8,12})',
        re.IGNORECASE,
    ),
    re.compile(r'\b([A-Z0-9]{8,12})\b\s+Confirmed', re.IGNORECASE),
    re.compile(r'Confirmed[.\s]+([A-Z0-9]{8,12})\b', re.IGNORECASE),
)

_AMOUNT_PATTERNS = (
    re.compile(r'Ksh\s*([\d,]+(?:\.\d{1,2})?)', re.IGNORECASE),
    re.compile(r'KES\s*([\d,]+(?:\.\d{1,2})?)', re.IGNORECASE),
    re.compile(r'paid\s+Ksh\s*([\d,]+(?:\.\d{1,2})?)', re.IGNORECASE),
)

_SKIP_RECEIPT_TOKENS = frozenset({
    'CONFIRMED', 'BALANCE', 'MPESA', 'SENT', 'RECEIVED', 'ACCOUNT', 'TRANSACTION',
})


def extract_mpesa_receipt_from_message(text: str) -> str:
    """Return M-Pesa receipt / confirmation code from pasted SMS text."""
    raw = (text or '').strip()
    if not raw:
        return ''
    for pattern in _RECEIPT_PATTERNS:
        match = pattern.search(raw)
        if match:
            return match.group(1).upper()
    upper = raw.upper()
    for match in re.finditer(r'\b([A-Z][A-Z0-9]{7,11})\b', upper):
        candidate = match.group(1)
        if candidate not in _SKIP_RECEIPT_TOKENS and 'CONFIRM' not in candidate:
            return candidate
    return ''


def parse_kes_amount_from_message(text: str) -> Decimal | None:
    """Extract paid amount from M-Pesa SMS when present."""
    raw = text or ''
    for pattern in _AMOUNT_PATTERNS:
        match = pattern.search(raw)
        if not match:
            continue
        digits = match.group(1).replace(',', '')
        try:
            return Decimal(digits).quantize(Decimal('0.01'))
        except InvalidOperation:
            continue
    return None


def is_valid_mpesa_receipt_code(receipt: str) -> bool:
    return bool(receipt and re.fullmatch(r'[A-Z0-9]{8,12}', receipt))