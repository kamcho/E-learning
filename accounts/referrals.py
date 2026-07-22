"""Referral codes, attribution, and subscription reward points."""

import secrets

from django.db import transaction
from django.db.models import F, Sum
from django.urls import reverse
from urllib.parse import urlencode

from .models import MyUser, ReferralPointLog, Role

REFERRAL_SUBSCRIBE_POINTS = 20
REFERRAL_SESSION_KEY = 'referral_code'


def generate_referral_code():
    while True:
        code = f'SK{secrets.token_hex(4).upper()[:8]}'
        if not MyUser.objects.filter(referral_code=code).exists():
            return code


def ensure_referral_code(user):
    """Assign a referral code to referral-role agents."""
    if not user.is_referral:
        return user.referral_code
    if user.referral_code:
        return user.referral_code
    code = generate_referral_code()
    MyUser.objects.filter(pk=user.pk).update(referral_code=code)
    user.referral_code = code
    return code


def resolve_referrer(code):
    code = (code or '').strip().upper()
    if not code:
        return None
    return (
        MyUser.objects
        .filter(referral_code__iexact=code, role=Role.REFERRAL, is_active=True)
        .first()
    )


def apply_referral_to_user(user, code):
    """Link a new user to the referral agent who referred them."""
    if user.referred_by_id:
        return user.referred_by
    referrer = resolve_referrer(code)
    if not referrer or referrer.pk == user.pk:
        return None
    user.referred_by = referrer
    user.save(update_fields=['referred_by', 'updated_at'])
    return referrer


def store_referral_code_in_session(request, code):
    code = (code or '').strip().upper()
    if code:
        request.session[REFERRAL_SESSION_KEY] = code


def pop_referral_code_from_session(request):
    return (request.session.pop(REFERRAL_SESSION_KEY, '') or '').strip().upper()


def award_referral_points_for_payment(payment):
    """
    Credit the referrer when a referred user completes a successful subscription payment.
    Idempotent per payment.
    """
    if payment.status != payment.Status.SUCCESS:
        return None

    referred_user = payment.user
    if not referred_user.referred_by_id:
        return None

    referrer = referred_user.referred_by
    if not referrer.is_referral:
        return None

    with transaction.atomic():
        log, created = ReferralPointLog.objects.get_or_create(
            payment=payment,
            defaults={
                'referrer': referrer,
                'referred_user': referred_user,
                'points': REFERRAL_SUBSCRIBE_POINTS,
            },
        )
        if not created:
            return None
        MyUser.objects.filter(pk=referrer.pk).update(
            referral_points=F('referral_points') + REFERRAL_SUBSCRIBE_POINTS,
        )
    return log


def build_referral_dashboard_context(user, request):
    from subscriptions.services import get_active_subscription
    from django.utils import timezone

    ensure_referral_code(user)
    user.refresh_from_db(fields=['referral_code', 'referral_points'])

    referred_qs = (
        MyUser.objects
        .filter(referred_by=user)
        .order_by('-date_joined')
    )
    referred_users = []
    subscribed_count = 0
    now = timezone.now()

    for referred in referred_qs:
        active_sub = get_active_subscription(referred)
        is_subscribed = active_sub is not None
        if is_subscribed:
            subscribed_count += 1
        referred_users.append({
            'user': referred,
            'is_subscribed': is_subscribed,
            'subscription_plan': active_sub.plan.name if active_sub else None,
            'joined_at': referred.date_joined,
        })

    point_logs = (
        ReferralPointLog.objects
        .filter(referrer=user)
        .select_related('referred_user', 'payment__plan')
        .order_by('-created_at')[:15]
    )

    total_points_earned = (
        ReferralPointLog.objects.filter(referrer=user).aggregate(total=Sum('points'))['total']
        or 0
    )

    signup_path = f"{reverse('accounts:signup')}?{urlencode({'ref': user.referral_code})}"
    referral_link = request.build_absolute_uri(signup_path)

    return {
        'referral_code': user.referral_code,
        'referral_link': referral_link,
        'referral_points': user.referral_points,
        'total_points_earned': total_points_earned,
        'referred_count': referred_qs.count(),
        'subscribed_count': subscribed_count,
        'referred_users': referred_users,
        'point_logs': point_logs,
        'points_per_subscription': REFERRAL_SUBSCRIBE_POINTS,
    }
