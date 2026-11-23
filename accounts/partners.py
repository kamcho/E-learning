"""Partner program — schools and teacher coordinators onboarding families & educators."""

from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Count, Sum
from django.urls import reverse
from django.utils import timezone

from subscriptions.services import get_active_subscription

from .models import MyUser, ReferralPointLog, Role, Student
from .referrals import (
    REFERRAL_SUBSCRIBE_POINTS,
    build_referral_dashboard_context,
    ensure_partner_code,
)


def _onboarding_links(request, partner_code):
    base = request.build_absolute_uri(reverse('accounts:signup'))
    ref = partner_code
    return {
        'family': f'{base}?{urlencode({"ref": ref})}',
        'teacher': f'{base}?{urlencode({"ref": ref, "role": Role.TEACHER})}',
        'school': f'{base}?{urlencode({"ref": ref, "role": Role.PARTNER})}',
    }


def _learners_linked_to_referred_guardians(partner):
    """Count distinct learners linked to guardians this partner referred."""
    guardian_ids = list(
        MyUser.objects.filter(referred_by=partner, role=Role.GUARDIAN).values_list('pk', flat=True),
    )
    if not guardian_ids:
        return 0
    return (
        Student.objects.filter(
            is_active=True,
            linked_students__user_id__in=guardian_ids,
        )
        .distinct()
        .count()
    )


def build_partner_dashboard_context(user, request):
    """Rich partner view: onboarding links, role mix, learners, and reward history."""
    user = MyUser.objects.get(pk=user.pk)
    ensure_partner_code(user)
    user.refresh_from_db(
        fields=[
            'referral_code',
            'referral_points',
            'county',
            'referral_commission_percent',
        ],
    )

    shared = build_referral_dashboard_context(user, request)
    referred_qs = MyUser.objects.filter(referred_by=user).order_by('-date_joined')

    role_counts = {
        row['role']: row['count']
        for row in referred_qs.values('role').annotate(count=Count('id'))
    }
    teachers_brought = role_counts.get(Role.TEACHER, 0)
    schools_brought = role_counts.get(Role.PARTNER, 0)
    families_brought = role_counts.get(Role.GUARDIAN, 0)

    referred_rows = []
    now = timezone.now()
    for referred in referred_qs[:50]:
        active_sub = get_active_subscription(referred)
        learner_count = len(referred.linked_learners()) if referred.is_guardian else 0
        referred_rows.append({
            'user': referred,
            'role_label': referred.get_role_display(),
            'joined_at': referred.date_joined,
            'is_subscribed': active_sub is not None,
            'subscription_plan': active_sub.plan.name if active_sub else None,
            'learner_count': learner_count,
        })

    payment_revenue = (
        ReferralPointLog.objects.filter(referrer=user)
        .aggregate(total=Sum('payment__amount_kes'))['total']
        or Decimal('0')
    )

    point_logs = (
        ReferralPointLog.objects.filter(referrer=user)
        .select_related('referred_user', 'payment__plan')
        .order_by('-created_at')[:20]
    )

    return {
        **shared,
        'partner': user,
        'onboarding_links': _onboarding_links(request, user.referral_code),
        'families_brought': families_brought,
        'teachers_brought': teachers_brought,
        'schools_brought': schools_brought,
        'learners_onboarded': _learners_linked_to_referred_guardians(user),
        'referred_rows': referred_rows,
        'payment_revenue_kes': payment_revenue,
        'point_logs': point_logs,
        'county_display': user.county_display or 'Not set',
    }