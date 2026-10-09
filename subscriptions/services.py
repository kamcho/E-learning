"""Subscription lifecycle and test-credit helpers."""

from django.db import transaction
from django.utils import timezone

from .models import Payment, Subscription, SubscriptionPlan, TestCreditLog


def _user_bypasses_subscription(user):
    return user.is_authenticated and user.is_platform_admin


def get_active_subscription(user):
    if not user.is_authenticated:
        return None
    return (
        Subscription.objects
        .filter(
            user=user,
            status=Subscription.Status.ACTIVE,
            ends_at__gt=timezone.now(),
        )
        .select_related('plan')
        .order_by('-ends_at')
        .first()
    )


def user_can_start_exam(user):
    """Guardian can start a new exam if they have credits or unlimited access."""
    if not user.is_authenticated:
        return False
    if _user_bypasses_subscription(user):
        return True
    subscription = get_active_subscription(user)
    if not subscription:
        return False
    return subscription.has_tests_available


def user_has_active_subscription(user):
    """Backward-compatible alias used by views — means can start an exam."""
    return user_can_start_exam(user)


def user_has_subscription_period(user):
    """True if the user has a time-valid subscription (even with zero credits)."""
    if not user.is_authenticated:
        return False
    if _user_bypasses_subscription(user):
        return True
    return get_active_subscription(user) is not None


def _credits_for_plan(plan: SubscriptionPlan):
    if plan.plan_type == SubscriptionPlan.PlanType.UNLIMITED:
        return None
    return plan.max_tests or 0


def _log_credit_change(*, user, subscription, payment=None, attempt=None, delta, reason, note=''):
    balance_after = None
    if subscription and subscription.tests_remaining is not None:
        balance_after = subscription.tests_remaining
    TestCreditLog.objects.create(
        user=user,
        subscription=subscription,
        payment=payment,
        attempt=attempt,
        delta=delta,
        balance_after=balance_after,
        reason=reason,
        note=note[:255],
    )


@transaction.atomic
def activate_subscription_from_payment(payment: Payment):
    """Mark payment successful and grant or extend test credits."""
    if payment.status == Payment.Status.SUCCESS:
        return payment.subscription

    now = timezone.now()
    plan = payment.plan
    duration = timezone.timedelta(days=plan.duration_days)
    credits_granted = _credits_for_plan(plan)

    active = get_active_subscription(payment.user)

    if active:
        subscription = (
            Subscription.objects
            .select_for_update()
            .get(pk=active.pk)
        )
        payment.subscription = subscription
        payment.save(update_fields=['subscription', 'updated_at'])

        base_end = subscription.ends_at if subscription.ends_at and subscription.ends_at > now else now
        subscription.ends_at = base_end + duration

        if plan.plan_type == SubscriptionPlan.PlanType.UNLIMITED:
            subscription.tests_remaining = None
        elif subscription.tests_remaining is not None:
            subscription.tests_remaining += credits_granted or 0
        elif credits_granted:
            subscription.tests_remaining = credits_granted
    else:
        subscription = payment.subscription
        if subscription is None:
            subscription = Subscription.objects.create(
                user=payment.user,
                plan=plan,
                status=Subscription.Status.PENDING,
            )
            payment.subscription = subscription
            payment.save(update_fields=['subscription', 'updated_at'])

        subscription = (
            Subscription.objects
            .select_for_update()
            .get(pk=subscription.pk)
        )
        subscription.starts_at = now
        subscription.ends_at = now + duration
        subscription.tests_remaining = credits_granted
        subscription.tests_used = 0

    subscription.plan = plan
    subscription.status = Subscription.Status.ACTIVE
    subscription.save(update_fields=[
        'plan', 'status', 'starts_at', 'ends_at',
        'tests_remaining', 'tests_used', 'updated_at',
    ])

    payment.status = Payment.Status.SUCCESS
    payment.save(update_fields=['status', 'updated_at'])

    if credits_granted is not None:
        _log_credit_change(
            user=payment.user,
            subscription=subscription,
            payment=payment,
            delta=credits_granted,
            reason=TestCreditLog.Reason.PURCHASE,
            note=plan.name,
        )
    else:
        _log_credit_change(
            user=payment.user,
            subscription=subscription,
            payment=payment,
            delta=0,
            reason=TestCreditLog.Reason.PURCHASE,
            note=f'{plan.name} (unlimited)',
        )

    try:
        from accounts.referrals import award_referral_points_for_payment
        award_referral_points_for_payment(payment)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            'Failed to award referral points for payment %s', payment.uuid,
        )

    try:
        from messenger.services import send_payment_confirmation_sms
        send_payment_confirmation_sms(payment)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            'Failed to send payment confirmation SMS for %s', payment.uuid,
        )

    return subscription


@transaction.atomic
def consume_test_credit(user, attempt):
    """
    Deduct one test credit when a guardian starts a new exam attempt.
    No-op for unlimited plans, staff, or continuing in-progress attempts.
    """
    if _user_bypasses_subscription(user):
        return None

    subscription = get_active_subscription(user)
    if not subscription:
        raise ValueError('No active subscription')

    subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)

    if subscription.tests_remaining is None:
        return subscription

    if subscription.tests_remaining <= 0:
        raise ValueError('No test credits remaining')

    subscription.tests_remaining -= 1
    subscription.tests_used += 1
    subscription.save(update_fields=['tests_remaining', 'tests_used', 'updated_at'])

    _log_credit_change(
        user=user,
        subscription=subscription,
        attempt=attempt,
        delta=-1,
        reason=TestCreditLog.Reason.CONSUME,
        note=str(attempt.quiz_id),
    )
    return subscription


def cancel_payment(payment: Payment, *, result_code=None, result_description=''):
    payment.status = Payment.Status.CANCELLED
    if result_code is not None:
        payment.result_code = result_code
    if result_description:
        payment.result_description = result_description[:255]
    payment.save(update_fields=['status', 'result_code', 'result_description', 'updated_at'])
    if payment.subscription and payment.subscription.status == Subscription.Status.PENDING:
        payment.subscription.status = Subscription.Status.CANCELLED
        payment.subscription.save(update_fields=['status', 'updated_at'])
    return payment


def fail_payment(payment: Payment, *, result_code=None, result_description=''):
    payment.status = Payment.Status.FAILED
    if result_code is not None:
        payment.result_code = result_code
    if result_description:
        payment.result_description = result_description[:255]
    payment.save(update_fields=['status', 'result_code', 'result_description', 'updated_at'])
    if payment.subscription and payment.subscription.status == Subscription.Status.PENDING:
        payment.subscription.status = Subscription.Status.CANCELLED
        payment.subscription.save(update_fields=['status', 'updated_at'])
    return payment


def parse_stk_callback(payload: dict):
    """Extract STK callback fields from Safaricom JSON body."""
    callback = payload.get('Body', {}).get('stkCallback', {})
    metadata_items = callback.get('CallbackMetadata', {}).get('Item', [])
    metadata = {}
    for item in metadata_items:
        name = item.get('Name')
        if name and 'Value' in item:
            metadata[name] = item['Value']

    return {
        'merchant_request_id': callback.get('MerchantRequestID', ''),
        'checkout_request_id': callback.get('CheckoutRequestID', ''),
        'result_code': callback.get('ResultCode'),
        'result_description': callback.get('ResultDesc', ''),
        'amount': metadata.get('Amount'),
        'mpesa_receipt_number': metadata.get('MpesaReceiptNumber', ''),
        'phone_number': metadata.get('PhoneNumber'),
        'transaction_date': metadata.get('TransactionDate'),
    }
