"""Safaricom Daraja M-Pesa STK Push client."""

from __future__ import annotations

import base64
import logging
from datetime import datetime

import requests
from django.conf import settings
from requests.exceptions import JSONDecodeError, RequestException

logger = logging.getLogger(__name__)

SANDBOX_SHORTCODE = '174379'


class MpesaConfigError(Exception):
    """Raised when required M-Pesa settings are missing."""


class MpesaAPIError(Exception):
    """Raised when the Daraja API returns an error response."""

    def __init__(self, message, response_data=None):
        super().__init__(message)
        self.response_data = response_data or {}


def _mpesa_settings():
    required = {
        'MPESA_CONSUMER_KEY': settings.MPESA_CONSUMER_KEY,
        'MPESA_CONSUMER_SECRET': settings.MPESA_CONSUMER_SECRET,
        'MPESA_SHORTCODE': settings.MPESA_SHORTCODE,
        'MPESA_PASSKEY': settings.MPESA_PASSKEY,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise MpesaConfigError(
            f'Missing M-Pesa configuration: {", ".join(missing)}. '
            'Set them in your .env file.'
        )
    return required


def mpesa_base_url():
    if settings.MPESA_ENVIRONMENT == 'production':
        return 'https://api.safaricom.co.ke'
    return 'https://sandbox.safaricom.co.ke'


def _environment_hint():
    env = (settings.MPESA_ENVIRONMENT or 'sandbox').strip().lower()
    shortcode = str(settings.MPESA_SHORTCODE or '').strip()
    if env != 'production' and shortcode and shortcode != SANDBOX_SHORTCODE:
        return (
            ' Your paybill/till looks like a live shortcode, but MPESA_ENVIRONMENT '
            'is sandbox. Set MPESA_ENVIRONMENT=production in .env (or use sandbox '
            f'shortcode {SANDBOX_SHORTCODE}).'
        )
    if env == 'production' and shortcode == SANDBOX_SHORTCODE:
        return (
            ' MPESA_ENVIRONMENT is production but the shortcode is the sandbox till '
            f'({SANDBOX_SHORTCODE}). Use sandbox, or a live shortcode.'
        )
    return ''


def _parse_daraja_json(response, action: str):
    """Parse a Daraja HTTP body; never leak raw JSON decode errors to users."""
    text = (response.text or '').strip()
    if not text:
        logger.error('%s empty body status=%s url=%s', action, response.status_code, response.url)
        raise MpesaAPIError(
            f'M-Pesa {action} returned an empty response (HTTP {response.status_code}).'
            f'{_environment_hint()}'
        )
    try:
        return response.json()
    except (ValueError, JSONDecodeError):
        snippet = ' '.join(text.split())[:180]
        logger.error(
            '%s non-JSON status=%s url=%s body=%s',
            action,
            response.status_code,
            response.url,
            snippet,
        )
        raise MpesaAPIError(
            f'M-Pesa {action} failed (HTTP {response.status_code}). '
            'Confirm consumer key/secret and that MPESA_ENVIRONMENT matches the Daraja app.'
            f'{_environment_hint()}'
        ) from None


def normalize_mpesa_phone(phone: str) -> str:
    """Normalize Kenyan numbers to 2547XXXXXXXX."""
    digits = ''.join(ch for ch in (phone or '') if ch.isdigit())
    if digits.startswith('254') and len(digits) == 12:
        return digits
    if digits.startswith('0') and len(digits) == 10:
        return f'254{digits[1:]}'
    if len(digits) == 9 and digits[0] in '17':
        return f'254{digits}'
    raise ValueError('Enter a valid Kenyan mobile number (e.g. 0712345678).')


def get_access_token() -> str:
    cfg = _mpesa_settings()
    url = f'{mpesa_base_url()}/oauth/v1/generate?grant_type=client_credentials'
    credentials = base64.b64encode(
        f'{cfg["MPESA_CONSUMER_KEY"]}:{cfg["MPESA_CONSUMER_SECRET"]}'.encode(),
    ).decode()
    try:
        response = requests.get(
            url,
            headers={'Authorization': f'Basic {credentials}'},
            timeout=30,
        )
    except RequestException as exc:
        logger.exception('M-Pesa OAuth request failed')
        raise MpesaAPIError('Could not reach M-Pesa. Check your internet connection.') from exc
    data = _parse_daraja_json(response, 'authentication')
    if response.status_code != 200 or 'access_token' not in data:
        logger.error('M-Pesa OAuth failed: %s', data)
        error = data.get('errorMessage') or data.get('error_description') or 'Could not authenticate with M-Pesa.'
        raise MpesaAPIError(f'{error}{_environment_hint()}', data)
    return data['access_token']


def _build_password(shortcode: str, passkey: str, timestamp: str) -> str:
    raw = f'{shortcode}{passkey}{timestamp}'
    return base64.b64encode(raw.encode()).decode()


def initiate_stk_push(*, phone_number: str, amount: int, account_reference: str, description: str):
    """
    Trigger Lipa na M-Pesa STK push.

    Returns dict with MerchantRequestID and CheckoutRequestID.
    """
    cfg = _mpesa_settings()
    token = get_access_token()
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    shortcode = cfg['MPESA_SHORTCODE']
    callback_base = (
        getattr(settings, 'MPESA_CALLBACK_BASE_URL', '')
        or getattr(settings, 'MPESA_CALLBACK_URL', '')
        or 'http://127.0.0.1:8000'
    )
    callback_url = (
        f'{str(callback_base).rstrip("/")}'
        f'/subscriptions/mpesa/callback/'
    )

    payload = {
        'BusinessShortCode': shortcode,
        'Password': _build_password(shortcode, cfg['MPESA_PASSKEY'], timestamp),
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        'Amount': int(amount),
        'PartyA': phone_number,
        'PartyB': shortcode,
        'PhoneNumber': phone_number,
        'CallBackURL': callback_url,
        'AccountReference': account_reference[:12],
        'TransactionDesc': description[:13],
    }

    url = f'{mpesa_base_url()}/mpesa/stkpush/v1/processrequest'
    try:
        response = requests.post(
            url,
            json=payload,
            headers={'Authorization': f'Bearer {token}'},
            timeout=30,
        )
    except RequestException as exc:
        logger.exception('STK push request failed')
        raise MpesaAPIError('Could not reach M-Pesa to send the STK push.') from exc
    data = _parse_daraja_json(response, 'STK push')
    if response.status_code != 200 or str(data.get('ResponseCode')) != '0':
        logger.error('STK push failed: %s', data)
        raise MpesaAPIError(
            data.get('CustomerMessage')
            or data.get('ResponseDescription')
            or data.get('errorMessage')
            or 'STK push request failed.',
            data,
        )
    return data


def query_stk_status(checkout_request_id: str):
    """Query STK transaction status (useful for polling)."""
    cfg = _mpesa_settings()
    token = get_access_token()
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    shortcode = cfg['MPESA_SHORTCODE']
    payload = {
        'BusinessShortCode': shortcode,
        'Password': _build_password(shortcode, cfg['MPESA_PASSKEY'], timestamp),
        'Timestamp': timestamp,
        'CheckoutRequestID': checkout_request_id,
    }
    url = f'{mpesa_base_url()}/mpesa/stkpushquery/v1/query'
    try:
        response = requests.post(
            url,
            json=payload,
            headers={'Authorization': f'Bearer {token}'},
            timeout=30,
        )
    except RequestException as exc:
        logger.exception('STK query request failed')
        raise MpesaAPIError('Could not reach M-Pesa to check payment status.') from exc
    return _parse_daraja_json(response, 'STK query')
