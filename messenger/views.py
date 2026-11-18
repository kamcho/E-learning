import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .support import apply_message_status, handle_inbound_message
from .whatsapp_cloud import verify_webhook_signature, whatsapp_is_configured

# Create your views here.

logger = logging.getLogger(__name__)
MAX_WEBHOOK_BYTES = 1_000_000


def _text_from_message(message):
    message_type = message.get('type', 'unknown')
    if message_type == 'text':
        return (message.get('text') or {}).get('body', ''), message_type
    if message_type == 'interactive':
        interactive = message.get('interactive') or {}
        button = interactive.get('button_reply') or {}
        list_reply = interactive.get('list_reply') or {}
        return button.get('title') or list_reply.get('title') or '', message_type
    if message_type == 'button':
        return (message.get('button') or {}).get('text', ''), message_type
    return '', message_type


def _process_payload(payload):
    if payload.get('object') != 'whatsapp_business_account':
        return
    expected_phone_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
    for entry in payload.get('entry') or []:
        for change in entry.get('changes') or []:
            value = change.get('value') or {}
            metadata = value.get('metadata') or {}
            phone_id = metadata.get('phone_number_id')
            if expected_phone_id and phone_id and phone_id != expected_phone_id:
                logger.warning('Ignoring WhatsApp webhook event for unexpected phone number ID.')
                continue
            for status in value.get('statuses') or []:
                errors = status.get('errors') or []
                error_message = (errors[0].get('title') or errors[0].get('message') or '') if errors else ''
                apply_message_status(status.get('id'), status.get('status'), error_message)
            for message in value.get('messages') or []:
                sender = message.get('from')
                if not sender or not message.get('id'):
                    continue
                text, message_type = _text_from_message(message)
                try:
                    handle_inbound_message(
                        sender=sender,
                        provider_message_id=message['id'],
                        text=text,
                        message_type=message_type,
                    )
                except Exception:
                    # An acknowledged provider delivery is not reprocessed blindly;
                    # deduplication and support-message records preserve the audit trail.
                    logger.exception('Could not process WhatsApp inbound message %s', message['id'])


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def whatsapp_support_webhook(request):
    """Meta WhatsApp Cloud API verification and signed inbound event endpoint."""
    if not getattr(settings, 'WHATSAPP_SUPPORT_ENABLED', False):
        return HttpResponse('WhatsApp support is disabled.', status=503)
    if not whatsapp_is_configured():
        return HttpResponse('WhatsApp support is not fully configured.', status=503)

    if request.method == 'GET':
        if (
            request.GET.get('hub.mode') == 'subscribe'
            and request.GET.get('hub.verify_token') == settings.WHATSAPP_VERIFY_TOKEN
        ):
            return HttpResponse(request.GET.get('hub.challenge', ''), content_type='text/plain')
        return HttpResponse('Webhook verification failed.', status=403)

    if len(request.body) > MAX_WEBHOOK_BYTES:
        return HttpResponse('Payload too large.', status=413)
    if not verify_webhook_signature(request.body, request.headers.get('X-Hub-Signature-256', '')):
        return HttpResponse('Invalid webhook signature.', status=403)
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse('Invalid JSON payload.', status=400)
    if not isinstance(payload, dict):
        return HttpResponse('Invalid webhook payload.', status=400)

    _process_payload(payload)
    return JsonResponse({'ok': True})
