import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class SmsMessage(models.Model):
    class Purpose(models.TextChoices):
        PAYMENT_SUCCESS = 'payment_success', 'Payment success'
        GENERAL = 'general', 'General'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'
        SKIPPED = 'skipped', 'Skipped'

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sms_messages',
    )
    payment = models.ForeignKey(
        'subscriptions.Payment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sms_messages',
    )
    phone_number = models.CharField(max_length=20)
    message = models.TextField()
    purpose = models.CharField(
        max_length=30,
        choices=Purpose.choices,
        default=Purpose.GENERAL,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    provider_message_id = models.CharField(max_length=64, blank=True)
    provider_response = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['purpose', 'status']),
            models.Index(fields=['payment', 'purpose']),
        ]

    def __str__(self):
        return f'SMS to {self.phone_number} ({self.get_status_display()})'


class WhatsAppConversation(models.Model):
    phone_number = models.CharField(max_length=20, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_support_conversations',
    )
    needs_human = models.BooleanField(default=False, db_index=True)
    opted_out_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ('-last_message_at',)

    def __str__(self):
        return f'WhatsApp support · {self.phone_number}'


class WhatsAppSupportMessage(models.Model):
    class Direction(models.TextChoices):
        INBOUND = 'inbound', 'Inbound'
        OUTBOUND = 'outbound', 'Outbound'

    class Status(models.TextChoices):
        RECEIVED = 'received', 'Received'
        SENT = 'sent', 'Sent'
        DELIVERED = 'delivered', 'Delivered'
        READ = 'read', 'Read'
        FAILED = 'failed', 'Failed'

    conversation = models.ForeignKey(
        WhatsAppConversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_support_messages',
    )
    direction = models.CharField(max_length=10, choices=Direction.choices)
    body = models.TextField()
    provider_message_id = models.CharField(max_length=160, unique=True, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    error_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('created_at',)
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
            models.Index(fields=['direction', 'status', 'created_at']),
        ]

    def __str__(self):
        return f'{self.get_direction_display()} WhatsApp message · {self.conversation.phone_number}'
