from django.contrib import admin
from django.utils import timezone
from datetime import timedelta

from .models import SmsMessage, WhatsAppConversation, WhatsAppSupportMessage


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


class WhatsAppSupportMessageInline(admin.TabularInline):
    model = WhatsAppSupportMessage
    extra = 0
    can_delete = False
    fields = ('created_at', 'direction', 'status', 'body', 'provider_message_id', 'error_message')
    readonly_fields = fields
    ordering = ('created_at',)


@admin.register(WhatsAppConversation)
class WhatsAppConversationAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'user', 'needs_human', 'opted_out_at', 'last_message_at')
    list_filter = ('needs_human', 'opted_out_at', 'updated_at')
    search_fields = ('phone_number', 'user__phone', 'user__first_name', 'user__last_name')
    readonly_fields = ('phone_number', 'user', 'created_at', 'updated_at', 'last_message_at')
    list_select_related = ('user',)
    inlines = (WhatsAppSupportMessageInline,)


@admin.register(WhatsAppSupportMessage)
class WhatsAppSupportMessageAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'conversation', 'user', 'direction', 'status', 'provider_message_id')
    list_filter = ('direction', 'status', 'created_at')
    search_fields = ('conversation__phone_number', 'body', 'provider_message_id', 'user__phone')
    readonly_fields = ('conversation', 'user', 'direction', 'body', 'provider_message_id', 'status', 'error_message', 'created_at', 'sent_at')
    list_select_related = ('conversation', 'user')
    date_hierarchy = 'created_at'
    actions = ('retry_failed_replies',)

    @admin.action(description='Retry selected failed WhatsApp replies')
    def retry_failed_replies(self, request, queryset):
        from .support import _send_reply

        retried = 0
        for message in queryset.filter(
            direction=WhatsAppSupportMessage.Direction.OUTBOUND,
            status=WhatsAppSupportMessage.Status.FAILED,
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).select_related('conversation', 'user')[:50]:
            if message.user_id and message.conversation.user_id != message.user_id:
                continue
            _send_reply(message.conversation, message.user, message.body)
            retried += 1
        self.message_user(request, f'Retried {retried} failed reply/replies.')
