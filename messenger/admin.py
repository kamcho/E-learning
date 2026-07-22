from django.contrib import admin

from .models import SmsMessage


@admin.register(SmsMessage)
class SmsMessageAdmin(admin.ModelAdmin):
    list_display = (
        'phone_number', 'purpose', 'status', 'user', 'payment',
        'provider_message_id', 'created_at', 'sent_at',
    )
    list_filter = ('status', 'purpose', 'created_at')
    search_fields = ('phone_number', 'message', 'provider_message_id', 'user__phone')
    readonly_fields = (
        'uuid', 'created_at', 'sent_at', 'provider_response',
    )
    raw_id_fields = ('user', 'payment')
