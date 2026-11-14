"""Safaricom Daraja Pull Transactions API (C2B reconciliation)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.utils import timezone
from requests.exceptions import RequestException

from .mpesa import (
    MpesaAPIError,
    MpesaConfigError,
    _mpesa_settings,
    _parse_daraja_json,
    get_access_token,
    mpesa_base_url,
    normalize_mpesa_phone,
)

logger = logging.getLogger(__name__)

MAX_PULL_PAGES = 25
PULL_PAGE_SIZE_HINT = 100


def _pull_callback_url() -> str:
    callback_base = (
        getattr(settings, 'MPESA_CALLBACK_BASE_URL', '')
        or getattr(settings, 'MPESA_CALLBACK_URL', '')
        or 'http://127.0.0.1:8000'
    )
    return f'{str(callback_base).rstrip("/")}/subscriptions/mpesa/pull-register-callback/'


def register_pull_transactions(*, nominated_number: str | None = None) -> dict:
    """
    One-time shortcode registration for Pull Transactions.

    See: https://developer.safaricom.co.ke/APIs/PullTransaction
    """
    _mpesa_settings()
    shortcode = str(settings.MPESA_SHORTCODE).strip()
    msisdn = normalize_mpesa_phone(
        nominated_number or getattr(settings, 'MPESA_PULL_NOMINATED_NUMBER', '') or '',
    )
    token = get_access_token()
    payload = {
        'ShortCode': shortcode,
        'RequestType': 'Pull',
        'NominatedNumber': msisdn,
        'CallBackURL': _pull_callback_url(),
    }
    url = f'{mpesa_base_url()}/pulltransactions/v1/register'
    try:
        response = requests.post(
            url,
            json=payload,
            headers={'Authorization': f'Bearer {token}'},
            timeout=45,
        )
    except RequestException as exc:
        logger.exception('Pull register request failed')
        raise MpesaAPIError('Could not reach M-Pesa to register Pull Transactions.') from exc
    return _parse_daraja_json(response, 'Pull register')


def _format_pull_datetime(dt: datetime) -> str:
    local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
    return local.strftime('%Y-%m-%d %H:%M:%S')


def query_pull_transactions(
    start: datetime,
    end: datetime,
    *,
    offset: int = 0,
) -> dict:
    """Query C2B transactions for the pay bill within the last 48 hours."""
    _mpesa_settings()
    shortcode = str(settings.MPESA_SHORTCODE).strip()
    token = get_access_token()
    payload = {
        'ShortCode': shortcode,
        'StartDate': _format_pull_datetime(start),
        'EndDate': _format_pull_datetime(end),
        'OffSetValue': str(int(offset)),
    }
    url = f'{mpesa_base_url()}/pulltransactions/v1/query'
    try:
        response = requests.post(
            url,
            json=payload,
            headers={'Authorization': f'Bearer {token}'},
            timeout=45,
        )
    except RequestException as exc:
        logger.exception('Pull query request failed')
        raise MpesaAPIError('Could not reach M-Pesa to pull transactions.') from exc
    return _parse_daraja_json(response, 'Pull query')


def normalize_pull_rows(data: dict) -> list[dict]:
    """Flatten Daraja pull query response into consistent rows."""
    raw = data.get('Response') or data.get('response') or []
    if raw and isinstance(raw, list) and raw and isinstance(raw[0], list):
        items = []
        for chunk in raw:
            if isinstance(chunk, list):
                items.extend(chunk)
            elif isinstance(chunk, dict):
                items.append(chunk)
        raw = items
    rows = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        transaction_id = (
            item.get('transactionId')
            or item.get('TransactionID')
            or item.get('transactionID')
            or ''
        )
        rows.append({
            'transaction_id': str(transaction_id).strip().upper(),
            'amount': item.get('amount') or item.get('Amount') or '',
            'msisdn': str(item.get('msisdn') or item.get('MSISDN') or item.get('Msisdn') or ''),
            'bill_reference': item.get('billreference') or item.get('BillRefNumber') or '',
            'transaction_type': item.get('transactiontype') or item.get('TransactionType') or '',
            'trx_date': item.get('trxDate') or item.get('TrxDate') or '',
            'raw': item,
        })
    return rows


def _parse_pull_amount(value) -> Decimal | None:
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value).replace(',', '')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def verify_receipt_via_pull_transactions(
    *,
    receipt: str,
    phone_number: str,
    amount_kes,
    payment_created_at: datetime,
) -> dict | None:
    """
    Find a successful pay-bill transaction by M-Pesa receipt (transactionId).

    Returns the matched normalized row, or None if not found in the query window.
    """
    receipt = (receipt or '').strip().upper()
    expected_amount = Decimal(str(amount_kes)).quantize(Decimal('0.01'))
    try:
        expected_phone = normalize_mpesa_phone(phone_number)
    except ValueError:
        expected_phone = ''.join(ch for ch in phone_number if ch.isdigit())

    now = timezone.now()
    window_start = max(
        payment_created_at - timedelta(minutes=15),
        now - timedelta(hours=47),
    )
    window_end = now + timedelta(minutes=5)

    offset = 0
    for _ in range(MAX_PULL_PAGES):
        data = query_pull_transactions(window_start, window_end, offset=offset)
        response_code = str(
            data.get('ResponseCode') or data.get('responseCode') or data.get('ResponseStatus') or '',
        )
        if response_code not in ('', '0', '1000'):
            message = (
                data.get('ResponseDescription')
                or data.get('responseMessage')
                or data.get('errorMessage')
                or 'Pull query failed.'
            )
            raise MpesaAPIError(message, data)

        rows = normalize_pull_rows(data)
        if not rows:
            break

        for row in rows:
            if row['transaction_id'] != receipt:
                continue
            pulled_amount = _parse_pull_amount(row['amount'])
            if pulled_amount is None or pulled_amount != expected_amount:
                raise MpesaAPIError(
                    f'Receipt {receipt} found but amount was {row["amount"]}, expected {expected_amount}.',
                    row,
                )
            row_msisdn = row['msisdn']
            try:
                row_phone = normalize_mpesa_phone(row_msisdn) if row_msisdn else ''
            except ValueError:
                row_phone = ''.join(ch for ch in row_msisdn if ch.isdigit())
            if row_phone and expected_phone and row_phone != expected_phone:
                raise MpesaAPIError(
                    'Receipt found but the paying phone number does not match this payment.',
                    row,
                )
            return row

        if len(rows) < PULL_PAGE_SIZE_HINT:
            break
        offset += len(rows)

    return None