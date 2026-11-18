"""Meta WhatsApp Cloud API transport and webhook signature helpers."""

import hashlib
import hmac
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class WhatsAppConfigurationError(Exception):
    pass


class WhatsAppAPIError(Exception):
    pass


def whatsapp_is_configured():
    return all((
        getattr(settings, 'WHATSAPP_VERIFY_TOKEN', ''),
        getattr(settings, 'WHATSAPP_APP_SECRET', ''),
        getattr(settings, 'WHATSAPP_ACCESS_TOKEN', ''),
        getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', ''),
    ))


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    secret = getattr(settings, 'WHATSAPP_APP_SECRET', '')
    if not secret or not signature.startswith('sha256='):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.partition('=')[2])


def send_whatsapp_text(*, to: str, body: str) -> dict:
    required = (
        getattr(settings, 'WHATSAPP_ACCESS_TOKEN', ''),
        getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', ''),
    )
    if not all(required):
        raise WhatsAppConfigurationError('WhatsApp Cloud API credentials are not configured.')

    version = getattr(settings, 'WHATSAPP_GRAPH_API_VERSION', 'v27.0')
    url = f'https://graph.facebook.com/{version}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages'
    try:
        response = requests.post(
            url,
            headers={
                'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
                'Content-Type': 'application/json',
            },
            json={
                'messaging_product': 'whatsapp',
                'recipient_type': 'individual',
                'to': to,
                'type': 'text',
                'text': {'preview_url': False, 'body': body[:4096]},
            },
            timeout=float(getattr(settings, 'WHATSAPP_API_TIMEOUT', 8)),
        )
        data = response.json() if response.content else {}
    except requests.RequestException as exc:
        raise WhatsAppAPIError('Could not reach WhatsApp Cloud API.') from exc
    except ValueError as exc:
        raise WhatsAppAPIError('WhatsApp Cloud API returned invalid JSON.') from exc

    if not response.ok:
        error = data.get('error') or {}
        logger.warning('WhatsApp API error status=%s code=%s', response.status_code, error.get('code'))
        raise WhatsAppAPIError(error.get('message') or 'WhatsApp message send failed.')
    messages = data.get('messages') or []
    if not messages or not messages[0].get('id'):
        raise WhatsAppAPIError('WhatsApp did not return a message identifier.')
    return {'message_id': messages[0]['id'], 'response': data}
