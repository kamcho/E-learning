"""High-level SMS notification helpers."""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from .models import SmsMessage
from .textsms import TextSmsAPIError, TextSmsConfigError, normalize_kenyan_mobile, send_sms

logger = logging.getLogger(__name__)


def _format_payment_success_message(payment) -> str:
    user = payment.user
    plan = payment.plan
    subscription = payment.subscription
    receipt = payment.mpesa_receipt_number or 'N/A'
    ends_at = ''
    if subscription and subscription.ends_at:
        ends_at = subscription.ends_at.strftime('%d %b %Y')

    lines = [
        f'Hi {user.first_name},',
        f'Payment of KES {payment.amount_kes:.0f} for {plan.name} received.',
        f'Receipt: {receipt}.',
    ]
    if ends_at:
        lines.append(f'Your Soma Smart plan is active until {ends_at}.')
    else:
        lines.append('Your Soma Smart subscription is now active.')
    lines.append('Thank you!')
    return ' '.join(lines)


def send_payment_confirmation_sms(payment) -> SmsMessage | None:
    """
    Send a payment confirmation SMS when a subscription payment succeeds.
    Idempotent per payment — won't send twice for the same payment.
    """
    if not getattr(settings, 'TEXTSMS_ENABLED', True):
        logger.info('TextSMS disabled; skipping payment SMS for %s', payment.uuid)
        return None

    existing = SmsMessage.objects.filter(
        payment=payment,
        purpose=SmsMessage.Purpose.PAYMENT_SUCCESS,
        status=SmsMessage.Status.SENT,
    ).first()
    if existing:
        return existing

    phone = payment.phone_number or payment.user.phone
    try:
        normalized = normalize_kenyan_mobile(phone)
    except ValueError:
        sms = SmsMessage.objects.create(
            user=payment.user,
            payment=payment,
            phone_number=phone,
            message=_format_payment_success_message(payment),
            purpose=SmsMessage.Purpose.PAYMENT_SUCCESS,
            status=SmsMessage.Status.FAILED,
            error_message='Invalid phone number for SMS',
        )
        logger.warning('Invalid phone for payment %s: %s', payment.uuid, phone)
        return sms

    message_text = _format_payment_success_message(payment)
    sms = SmsMessage.objects.create(
        user=payment.user,
        payment=payment,
        phone_number=normalized,
        message=message_text,
        purpose=SmsMessage.Purpose.PAYMENT_SUCCESS,
        status=SmsMessage.Status.PENDING,
    )

    try:
        result = send_sms(mobile=normalized, message=message_text)
        sms.status = SmsMessage.Status.SENT
        sms.provider_message_id = result.get('message_id', '')
        sms.provider_response = result.get('raw', {})
        sms.sent_at = timezone.now()
        sms.save(update_fields=[
            'status', 'provider_message_id', 'provider_response', 'sent_at',
        ])
        logger.info('Payment SMS sent for payment %s to %s', payment.uuid, normalized)
    except TextSmsConfigError as exc:
        sms.status = SmsMessage.Status.SKIPPED
        sms.error_message = str(exc)[:255]
        sms.save(update_fields=['status', 'error_message'])
        logger.warning('TextSMS not configured: %s', exc)
    except TextSmsAPIError as exc:
        sms.status = SmsMessage.Status.FAILED
        sms.error_message = str(exc)[:255]
        sms.provider_response = getattr(exc, 'response_data', {}) or {}
        sms.save(update_fields=['status', 'error_message', 'provider_response'])
        logger.error('Payment SMS failed for %s: %s', payment.uuid, exc)

    return sms
