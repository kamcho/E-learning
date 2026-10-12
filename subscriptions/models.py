import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class SubscriptionPlan(models.Model):
    class PlanType(models.TextChoices):
        SINGLE_TEST = 'single_test', 'Single test'
        TEST_PACK = 'test_pack', 'Test pack'
        UNLIMITED = 'unlimited', 'Unlimited'

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    plan_type = models.CharField(
        max_length=20,
        choices=PlanType.choices,
        default=PlanType.TEST_PACK,
    )
    price_kes = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.PositiveIntegerField(default=30)
    max_tests = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Tests included in this plan. Leave blank for unlimited.',
    )
    max_learners = models.PositiveIntegerField(
        default=3,
        help_text='Maximum linked learners included in this plan.',
    )
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('sort_order', 'price_kes')

    def __str__(self):
        return f'{self.name} (KES {self.price_kes})'

    @property
    def is_unlimited(self):
        return self.plan_type == self.PlanType.UNLIMITED

    @property
    def tests_label(self):
        if self.is_unlimited:
            return 'Unlimited tests'
        if self.max_tests == 1:
            return '1 test'
        return f'{self.max_tests} tests'

    @property
    def duration_label(self):
        days = self.duration_days or 0
        if days == 7:
            return '7 days'
        if days == 30:
            return '30 days'
        if days == 365:
            return '1 year'
        return f'{days} day{"s" if days != 1 else ""}'

    @property
    def price_period_label(self):
        if self.plan_type == self.PlanType.SINGLE_TEST or self.max_tests == 1:
            return 'test'
        if self.duration_days == 7:
            return 'week'
        if self.duration_days == 30:
            return 'month'
        if (self.duration_days or 0) >= 360:
            return 'year'
        return self.duration_label

    @property
    def kes_per_test(self):
        if self.is_unlimited or not self.max_tests:
            return None
        return self.price_kes / self.max_tests


class Subscription(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        EXPIRED = 'expired', 'Expired'
        CANCELLED = 'cancelled', 'Cancelled'

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscriptions',
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='subscriptions',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    tests_remaining = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Null means unlimited tests for the active period.',
    )
    tests_used = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.user} — {self.plan.name} ({self.status})'

    @property
    def is_active_now(self):
        return (
            self.status == self.Status.ACTIVE
            and self.ends_at is not None
            and self.ends_at > timezone.now()
        )

    @property
    def is_unlimited(self):
        return self.tests_remaining is None

    @property
    def has_tests_available(self):
        if not self.is_active_now:
            return False
        if self.is_unlimited:
            return True
        return (self.tests_remaining or 0) > 0

    @property
    def tests_balance_label(self):
        if not self.is_active_now:
            return 'Expired'
        if self.is_unlimited:
            return 'Unlimited'
        remaining = self.tests_remaining or 0
        return f'{remaining} test{"s" if remaining != 1 else ""} left'


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription_payments',
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payments',
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='payments',
    )
    amount_kes = models.DecimalField(max_digits=10, decimal_places=2)
    phone_number = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    merchant_request_id = models.CharField(max_length=64, blank=True, db_index=True)
    checkout_request_id = models.CharField(max_length=64, blank=True, db_index=True)
    mpesa_receipt_number = models.CharField(max_length=32, blank=True)
    result_code = models.IntegerField(null=True, blank=True)
    result_description = models.CharField(max_length=255, blank=True)
    callback_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'Payment {self.uuid} — {self.status} — KES {self.amount_kes}'


class TestCreditLog(models.Model):
    """Audit trail for test credit purchases and consumption."""

    class Reason(models.TextChoices):
        PURCHASE = 'purchase', 'Purchase'
        CONSUME = 'consume', 'Exam started'
        ADJUST = 'adjust', 'Manual adjustment'

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='test_credit_logs',
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='credit_logs',
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='credit_logs',
    )
    attempt = models.ForeignKey(
        'core.UserAttempts',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='credit_logs',
    )
    delta = models.IntegerField(
        help_text='Positive when credits added, negative when consumed.',
    )
    balance_after = models.IntegerField(null=True, blank=True)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.user} {self.delta:+d} ({self.reason})'
