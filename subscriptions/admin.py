from django.contrib import admin

from .models import Payment, Subscription, SubscriptionPlan, TestCreditLog


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'slug', 'plan_type', 'price_kes', 'max_tests',
        'duration_days', 'is_active', 'sort_order',
    )
    list_filter = ('is_active', 'plan_type')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name', 'slug')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'plan', 'status', 'tests_remaining', 'tests_used',
        'starts_at', 'ends_at', 'created_at',
    )
    list_filter = ('status', 'plan')
    search_fields = ('user__phone', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user', 'plan')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'uuid', 'user', 'plan', 'amount_kes', 'status',
        'mpesa_receipt_number', 'created_at',
    )
    list_filter = ('status', 'plan')
    search_fields = (
        'user__phone', 'checkout_request_id', 'merchant_request_id',
        'mpesa_receipt_number',
    )
    raw_id_fields = ('user', 'subscription', 'plan')
    readonly_fields = ('callback_payload', 'created_at', 'updated_at')


@admin.register(TestCreditLog)
class TestCreditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'delta', 'balance_after', 'reason', 'created_at')
    list_filter = ('reason',)
    search_fields = ('user__phone', 'note')
    raw_id_fields = ('user', 'subscription', 'payment', 'attempt')
    readonly_fields = ('created_at',)
