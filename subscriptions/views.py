import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .forms import SubscribeForm
from .models import Payment, Subscription, SubscriptionPlan
from .mpesa import MpesaAPIError, MpesaConfigError, initiate_stk_push, query_stk_status
from .services import (
    activate_subscription_from_payment,
    cancel_payment,
    fail_payment,
    get_active_subscription,
    parse_stk_callback,
    user_has_active_subscription,
)

logger = logging.getLogger(__name__)

ADMIN_PAYMENTS_PAGE_SIZE = 20
ADMIN_SUBSCRIPTIONS_PAGE_SIZE = 20


def _admin_access_or_redirect(request):
    if not (request.user.is_authenticated and request.user.is_platform_admin):
        messages.error(request, "You don't have permission to view this page.")
        return redirect('core:landing')
    return None


def _pagination_extra_params(request, exclude_keys):
    params = request.GET.copy()
    for key in exclude_keys:
        params.pop(key, None)
    return params.urlencode()


def _get_admin_payments_queryset(*, search='', status=''):
    qs = (
        Payment.objects
        .select_related('user', 'plan')
        .order_by('-created_at')
    )
    if search:
        qs = qs.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__phone__icontains=search)
            | Q(user__email__icontains=search)
            | Q(mpesa_receipt_number__icontains=search)
            | Q(phone_number__icontains=search)
            | Q(plan__name__icontains=search)
            | Q(checkout_request_id__icontains=search)
        )
    if status:
        qs = qs.filter(status=status)
    return qs


def _build_admin_payment_stats():
    agg = Payment.objects.aggregate(
        total=Count('pk'),
        success_count=Count('pk', filter=Q(status=Payment.Status.SUCCESS)),
        pending_count=Count('pk', filter=Q(status=Payment.Status.PENDING)),
        failed_count=Count(
            'pk',
            filter=Q(status__in=[Payment.Status.FAILED, Payment.Status.CANCELLED]),
        ),
        revenue=Sum('amount_kes', filter=Q(status=Payment.Status.SUCCESS)),
    )
    return {
        'total': agg['total'] or 0,
        'success_count': agg['success_count'] or 0,
        'pending_count': agg['pending_count'] or 0,
        'failed_count': agg['failed_count'] or 0,
        'revenue': agg['revenue'] or 0,
    }


def _get_admin_subscriptions_queryset(*, search='', status=''):
    qs = (
        Subscription.objects
        .select_related('user', 'plan')
        .order_by('-created_at')
    )
    if search:
        qs = qs.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__phone__icontains=search)
            | Q(user__email__icontains=search)
            | Q(plan__name__icontains=search)
            | Q(plan__slug__icontains=search)
        )
    if status:
        qs = qs.filter(status=status)
    return qs


def _build_admin_subscription_stats():
    from django.utils import timezone

    now = timezone.now()
    agg = Subscription.objects.aggregate(
        total=Count('pk'),
        active_status=Count('pk', filter=Q(status=Subscription.Status.ACTIVE)),
        pending_count=Count('pk', filter=Q(status=Subscription.Status.PENDING)),
        expired_count=Count('pk', filter=Q(status=Subscription.Status.EXPIRED)),
        cancelled_count=Count('pk', filter=Q(status=Subscription.Status.CANCELLED)),
    )
    live_count = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        ends_at__gt=now,
    ).count()
    guardians_with_live = (
        Subscription.objects
        .filter(status=Subscription.Status.ACTIVE, ends_at__gt=now)
        .values('user_id')
        .distinct()
        .count()
    )
    return {
        'total': agg['total'] or 0,
        'live_count': live_count,
        'active_status': agg['active_status'] or 0,
        'pending_count': agg['pending_count'] or 0,
        'expired_count': agg['expired_count'] or 0,
        'cancelled_count': agg['cancelled_count'] or 0,
        'guardians_with_live': guardians_with_live,
    }


@login_required(login_url='accounts:signin')
def plans_view(request):
    plans = SubscriptionPlan.objects.filter(is_active=True)
    active_subscription = get_active_subscription(request.user)
    return render(request, 'subscriptions/plans.html', {
        'plans': plans,
        'active_subscription': active_subscription,
        'has_subscription': user_has_active_subscription(request.user),
    })


@login_required(login_url='accounts:signin')
def subscribe_view(request, plan_slug):
    plan = get_object_or_404(SubscriptionPlan, slug=plan_slug, is_active=True)
    initial_phone = request.user.phone or ''

    if request.method == 'POST':
        form = SubscribeForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data['phone_number']
            payment = Payment.objects.create(
                user=request.user,
                plan=plan,
                amount_kes=plan.price_kes,
                phone_number=phone,
                status=Payment.Status.PENDING,
            )
            try:
                stk_response = initiate_stk_push(
                    phone_number=phone,
                    amount=int(plan.price_kes),
                    account_reference=str(payment.uuid)[:12],
                    description=plan.name[:13],
                )
            except (MpesaConfigError, MpesaAPIError, ValueError) as exc:
                payment.status = Payment.Status.FAILED
                payment.result_description = str(exc)[:255]
                payment.save(update_fields=['status', 'result_description', 'updated_at'])
                messages.error(request, str(exc))
                return redirect('subscriptions:subscribe', plan_slug=plan.slug)

            payment.merchant_request_id = stk_response.get('MerchantRequestID', '')
            payment.checkout_request_id = stk_response.get('CheckoutRequestID', '')
            payment.save(update_fields=[
                'merchant_request_id', 'checkout_request_id', 'updated_at',
            ])
            messages.info(
                request,
                'STK push sent. Enter your M-Pesa PIN on your phone to complete payment.',
            )
            return redirect('subscriptions:payment_pending', payment_uuid=payment.uuid)
    else:
        form = SubscribeForm(initial={'phone_number': initial_phone})

    return render(request, 'subscriptions/subscribe.html', {
        'plan': plan,
        'form': form,
        'active_subscription': get_active_subscription(request.user),
    })


@login_required(login_url='accounts:signin')
def payment_pending_view(request, payment_uuid):
    payment = get_object_or_404(
        Payment,
        uuid=payment_uuid,
        user=request.user,
    )
    return render(request, 'subscriptions/payment_pending.html', {
        'payment': payment,
        'plan': payment.plan,
    })


@login_required(login_url='accounts:signin')
@require_GET
def payment_status_view(request, payment_uuid):
    payment = get_object_or_404(
        Payment,
        uuid=payment_uuid,
        user=request.user,
    )

    if payment.status == Payment.Status.PENDING and payment.checkout_request_id:
        try:
            query_data = query_stk_status(payment.checkout_request_id)
            result_code = query_data.get('ResultCode')
            if result_code == '0':
                activate_subscription_from_payment(payment)
                payment.refresh_from_db()
            elif str(result_code) == '1032':
                cancel_payment(
                    payment,
                    result_code=1032,
                    result_description=query_data.get('ResultDesc', 'Payment cancelled.'),
                )
                payment.refresh_from_db()
            elif result_code not in (None,) and str(result_code) != '4999':
                fail_payment(
                    payment,
                    result_code=int(result_code) if str(result_code).isdigit() else None,
                    result_description=query_data.get('ResultDesc', 'Payment failed.'),
                )
                payment.refresh_from_db()
        except (MpesaConfigError, MpesaAPIError) as exc:
            logger.warning('STK query failed for %s: %s', payment.uuid, exc)

    redirect_url = None
    if payment.status == Payment.Status.SUCCESS:
        redirect_url = reverse('subscriptions:my_subscription')

    return JsonResponse({
        'status': payment.status,
        'result_description': payment.result_description,
        'mpesa_receipt_number': payment.mpesa_receipt_number,
        'redirect_url': redirect_url,
    })


@csrf_exempt
@require_POST
def mpesa_callback_view(request):
    """
    Safaricom STK callback endpoint.

    Must be publicly reachable (use ngrok in local dev).
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning('Invalid M-Pesa callback payload')
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid payload'})

    parsed = parse_stk_callback(payload)
    checkout_id = parsed.get('checkout_request_id', '')
    merchant_id = parsed.get('merchant_request_id', '')

    payment = Payment.objects.filter(
        checkout_request_id=checkout_id,
    ).first()
    if not payment and merchant_id:
        payment = Payment.objects.filter(merchant_request_id=merchant_id).first()

    if not payment:
        logger.warning('M-Pesa callback for unknown payment: %s', checkout_id)
        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})

    payment.callback_payload = payload
    payment.result_code = parsed.get('result_code')
    payment.result_description = (parsed.get('result_description') or '')[:255]
    if parsed.get('mpesa_receipt_number'):
        payment.mpesa_receipt_number = parsed['mpesa_receipt_number']
    if parsed.get('phone_number'):
        payment.phone_number = str(parsed['phone_number'])
    payment.save(update_fields=[
        'callback_payload', 'result_code', 'result_description',
        'mpesa_receipt_number', 'phone_number', 'updated_at',
    ])

    if parsed.get('result_code') == 0:
        activate_subscription_from_payment(payment)
    elif parsed.get('result_code') == 1032:
        cancel_payment(
            payment,
            result_code=1032,
            result_description=parsed.get('result_description', 'Payment cancelled.'),
        )
    else:
        fail_payment(
            payment,
            result_code=parsed.get('result_code'),
            result_description=parsed.get('result_description', 'Payment failed.'),
        )

    return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})


@login_required(login_url='accounts:signin')
def my_subscription_view(request):
    from django.db.models import Sum
    from django.utils import timezone

    from subscriptions.models import SubscriptionPlan, TestCreditLog

    active = get_active_subscription(request.user)
    history = (
        request.user.subscriptions
        .select_related('plan')
        .order_by('-created_at')[:10]
    )
    payments = (
        request.user.subscription_payments
        .select_related('plan')
        .order_by('-created_at')[:12]
    )
    credit_logs = (
        TestCreditLog.objects
        .filter(user=request.user)
        .select_related('subscription', 'payment__plan')
        .order_by('-created_at')[:8]
    )
    quick_plans = SubscriptionPlan.objects.filter(is_active=True).order_by('sort_order')

    days_remaining = None
    usage_percent = 0
    tests_pool_total = None

    if active and active.ends_at:
        delta = active.ends_at - timezone.now()
        days_remaining = max(0, delta.days)

    if active and not active.is_unlimited:
        remaining = active.tests_remaining or 0
        tests_pool_total = remaining + active.tests_used
        if tests_pool_total:
            usage_percent = min(100, round((active.tests_used / tests_pool_total) * 100))

    total_spent = (
        request.user.subscription_payments
        .filter(status=Payment.Status.SUCCESS)
        .aggregate(total=Sum('amount_kes'))['total']
    ) or 0

    return render(request, 'subscriptions/my_subscription.html', {
        'active_subscription': active,
        'subscription_history': history,
        'payments': payments,
        'credit_logs': credit_logs,
        'quick_plans': quick_plans,
        'has_subscription': user_has_active_subscription(request.user),
        'days_remaining': days_remaining,
        'usage_percent': usage_percent,
        'tests_pool_total': tests_pool_total,
        'total_spent': total_spent,
    })


@login_required(login_url='accounts:signin')
def admin_payments_list_view(request):
    """Admin: paginated list of all M-Pesa subscription payments."""
    denied = _admin_access_or_redirect(request)
    if denied:
        return denied

    search = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    valid_statuses = {choice[0] for choice in Payment.Status.choices}
    if status and status not in valid_statuses:
        status = ''

    page_obj = Paginator(
        _get_admin_payments_queryset(search=search, status=status),
        ADMIN_PAYMENTS_PAGE_SIZE,
    ).get_page(request.GET.get('page'))

    return render(request, 'accounts/admin_payments_list.html', {
        'page_obj': page_obj,
        'search': search,
        'status_filter': status,
        'status_choices': Payment.Status.choices,
        'stats': _build_admin_payment_stats(),
        'pagination_extra': _pagination_extra_params(request, ['page']),
        'django_admin_url': reverse('admin:subscriptions_payment_changelist'),
    })


@login_required(login_url='accounts:signin')
def admin_subscriptions_list_view(request):
    """Admin: paginated list of user subscriptions and test credits."""
    denied = _admin_access_or_redirect(request)
    if denied:
        return denied

    search = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    valid_statuses = {choice[0] for choice in Subscription.Status.choices}
    if status and status not in valid_statuses:
        status = ''

    page_obj = Paginator(
        _get_admin_subscriptions_queryset(search=search, status=status),
        ADMIN_SUBSCRIPTIONS_PAGE_SIZE,
    ).get_page(request.GET.get('page'))

    return render(request, 'accounts/admin_subscriptions_list.html', {
        'page_obj': page_obj,
        'search': search,
        'status_filter': status,
        'status_choices': Subscription.Status.choices,
        'stats': _build_admin_subscription_stats(),
        'pagination_extra': _pagination_extra_params(request, ['page']),
        'django_admin_url': reverse('admin:subscriptions_subscription_changelist'),
    })
