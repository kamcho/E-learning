import hashlib
import json
import logging
import secrets
from urllib.parse import quote
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.ratelimit import rate_limit
from .forms import SubscribeForm
from .models import GuestDemoPayment, Payment, Subscription, SubscriptionPlan
from .mpesa import MpesaAPIError, MpesaConfigError, initiate_stk_push, query_stk_status
from .services import (
    activate_subscription_from_payment,
    cancel_payment,
    fail_payment,
    get_active_subscription,
    parse_stk_callback,
    user_has_active_subscription,
)
from .pricing import grade_band_for_grade, grade_band_for_student

logger = logging.getLogger(__name__)

ADMIN_PAYMENTS_PAGE_SIZE = 20
ADMIN_SUBSCRIPTIONS_PAGE_SIZE = 20


def _guest_demo_token_hash(request, *, create=False):
    token = request.session.get('guest_demo_payment_token')
    if not token and create:
        token = secrets.token_urlsafe(32)
        request.session['guest_demo_payment_token'] = token
    if not token:
        return ''
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _guest_demo_payment_for_request(request, payment_uuid):
    demo = request.session.get('practice_demo')
    if not demo or not demo.get('demo_id'):
        return None
    token_hash = _guest_demo_token_hash(request)
    if not token_hash:
        return None
    return GuestDemoPayment.objects.filter(
        uuid=payment_uuid,
        session_token_hash=token_hash,
        demo_id=demo['demo_id'],
    ).first()


def _update_guest_demo_payment(payment, parsed, *, callback_payload=None):
    raw_result_code = parsed.get('result_code')
    try:
        result_code = int(raw_result_code) if raw_result_code is not None else None
    except (TypeError, ValueError):
        result_code = None
    payment.result_code = result_code
    payment.result_description = (parsed.get('result_description') or '')[:255]
    if parsed.get('mpesa_receipt_number'):
        payment.mpesa_receipt_number = parsed['mpesa_receipt_number']
    if parsed.get('phone_number'):
        payment.phone_number = str(parsed['phone_number'])
    if callback_payload is not None:
        payment.callback_payload = callback_payload

    if payment.status == GuestDemoPayment.Status.PENDING:
        if result_code == 0:
            payment.status = GuestDemoPayment.Status.SUCCESS
        elif result_code == 1032:
            payment.status = GuestDemoPayment.Status.CANCELLED
        elif result_code is not None:
            payment.status = GuestDemoPayment.Status.FAILED

    payment.save(update_fields=[
        'result_code', 'result_description', 'mpesa_receipt_number',
        'phone_number', 'callback_payload', 'status', 'updated_at',
    ])


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


def _get_admin_guest_payments_queryset(*, search='', status=''):
    qs = GuestDemoPayment.objects.select_related('plan').order_by('-created_at')
    if search:
        qs = qs.filter(
            Q(mpesa_receipt_number__icontains=search)
            | Q(phone_number__icontains=search)
            | Q(plan__name__icontains=search)
            | Q(checkout_request_id__icontains=search)
            | Q(demo_id__icontains=search)
        )
    if status:
        qs = qs.filter(status=status)
    return qs


def _build_admin_payment_ledger(*, search='', status=''):
    """Merge guardian subscriptions and logged-out guest exam payments for admin UI."""
    ledger = []
    for payment in _get_admin_payments_queryset(search=search, status=status):
        ledger.append({
            'kind': 'subscription',
            'created_at': payment.created_at,
            'payment': payment,
        })
    for payment in _get_admin_guest_payments_queryset(search=search, status=status):
        ledger.append({
            'kind': 'guest_exam',
            'created_at': payment.created_at,
            'payment': payment,
        })
    ledger.sort(key=lambda row: row['created_at'], reverse=True)
    return ledger


def _aggregate_payment_stats(queryset):
    agg = queryset.aggregate(
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


def _build_admin_payment_stats():
    sub = _aggregate_payment_stats(Payment.objects.all())
    guest = _aggregate_payment_stats(GuestDemoPayment.objects.all())
    revenue = (sub['revenue'] or 0) + (guest['revenue'] or 0)
    return {
        'total': sub['total'] + guest['total'],
        'success_count': sub['success_count'] + guest['success_count'],
        'pending_count': sub['pending_count'] + guest['pending_count'],
        'failed_count': sub['failed_count'] + guest['failed_count'],
        'revenue': revenue,
    }


def _parse_admin_subscription_list_filters(request):
    """Read subscription-directory filters from the query string."""
    status = request.GET.get('status', '').strip()
    plan = request.GET.get('plan', '').strip()
    live = request.GET.get('live', '').strip()
    plan_type = request.GET.get('plan_type', '').strip()
    credits = request.GET.get('credits', '').strip()
    scope = request.GET.get('scope', '').strip()

    valid_statuses = {choice[0] for choice in Subscription.Status.choices}
    if status and status not in valid_statuses:
        status = ''

    valid_plan_types = {choice[0] for choice in SubscriptionPlan.PlanType.choices}
    if plan_type and plan_type not in valid_plan_types:
        plan_type = ''

    if live not in ('live', 'not_live'):
        live = ''

    if credits not in ('unlimited', 'has_remaining', 'depleted'):
        credits = ''

    if scope not in ('guardian', 'learner'):
        scope = ''

    if plan:
        try:
            UUID(plan)
        except (TypeError, ValueError):
            plan = ''

    return {
        'search': request.GET.get('q', '').strip(),
        'status': status,
        'plan': plan,
        'live': live,
        'plan_type': plan_type,
        'credits': credits,
        'scope': scope,
    }


def _admin_subscription_list_has_filters(filters):
    return bool(filters.get('search') or any(
        filters.get(key) for key in ('status', 'plan', 'live', 'plan_type', 'credits', 'scope')
    ))


def _get_admin_subscriptions_queryset(
    *,
    search='',
    status='',
    plan='',
    live='',
    plan_type='',
    credits='',
    scope='',
):
    from django.utils import timezone

    qs = (
        Subscription.objects
        .select_related('user', 'plan', 'student')
        .order_by('-created_at')
    )
    if search:
        qs = qs.filter(
            Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(user__phone__icontains=search)
            | Q(user__email__icontains=search)
            | Q(student__first_name__icontains=search)
            | Q(student__last_name__icontains=search)
            | Q(plan__name__icontains=search)
            | Q(plan__slug__icontains=search)
        )
    if status:
        qs = qs.filter(status=status)
    if plan:
        qs = qs.filter(plan_id=plan)
    if plan_type:
        qs = qs.filter(plan__plan_type=plan_type)
    if scope == 'guardian':
        qs = qs.filter(student__isnull=True)
    elif scope == 'learner':
        qs = qs.filter(student__isnull=False)
    if live == 'live':
        now = timezone.now()
        qs = qs.filter(
            status=Subscription.Status.ACTIVE,
            ends_at__gt=now,
        )
    elif live == 'not_live':
        now = timezone.now()
        qs = qs.exclude(
            status=Subscription.Status.ACTIVE,
            ends_at__gt=now,
        )
    if credits == 'unlimited':
        qs = qs.filter(tests_remaining__isnull=True)
    elif credits == 'has_remaining':
        qs = qs.filter(tests_remaining__gt=0)
    elif credits == 'depleted':
        qs = qs.filter(tests_remaining=0)
    return qs.distinct()


def _admin_subscription_plan_choices():
    return list(
        SubscriptionPlan.objects
        .filter(subscriptions__isnull=False)
        .distinct()
        .order_by('sort_order', 'name')
    )


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
    student = None
    next_url = request.GET.get('next', '').strip()

    if plan.grade_band:
        from accounts.models import Student

        student_uuid = request.GET.get('student', '')
        if request.method == 'POST' and request.POST.get('student') != student_uuid:
            messages.error(request, 'The learner selection changed. Please choose the exam again.')
            return redirect('core:exams_list')
        try:
            student_pk = UUID(student_uuid)
        except ValueError:
            student_pk = None
        if student_pk:
            student = Student.objects.filter(uuid=student_pk).select_related('grade_level').first()
        if not student or not request.user.is_guardian or not request.user.linked_students.filter(
            students=student,
        ).exists():
            messages.error(request, 'Choose one of your linked learners to pay for their exam.')
            return redirect('core:exams_list')
        if grade_band_for_student(student) != plan.grade_band:
            messages.error(request, 'That price does not match the selected learner’s grade.')
            return redirect('core:exams_list')

    if request.method == 'POST':
        form = SubscribeForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data['phone_number']
            payment = Payment.objects.create(
                user=request.user,
                student=student,
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
                retry_url = reverse('subscriptions:subscribe', kwargs={'plan_slug': plan.slug})
                query = []
                if student:
                    query.append(f'student={student.uuid}')
                if next_url:
                    query.append(f'next={quote(next_url, safe="")}')
                return redirect(f'{retry_url}?{"&".join(query)}' if query else retry_url)

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
        'student': student,
        'next_url': next_url,
        'form': form,
        'active_subscription': get_active_subscription(request.user, student),
    })


@require_http_methods(['GET', 'POST'])
@rate_limit(
    key='guest_demo_checkout',
    limit=5,
    window=3600,
    by='ip',
    methods=['POST'],
    json_error='Too many payment attempts. Please wait and try again.',
)
def guest_demo_checkout_view(request):
    from core.demo import get_demo_session

    demo = get_demo_session(request)
    if not demo or demo.get('completed'):
        return redirect('core:exam_wizard')
    if request.user.is_authenticated:
        return redirect('core:exam_take')
    if len(demo.get('answers', {})) < 3:
        return redirect('core:exam_take')
    from core.demo_views import _guest_demo_payment_succeeded

    if _guest_demo_payment_succeeded(request, demo):
        return redirect('core:exam_take')

    from subjects.models import GradeLevel

    grade = GradeLevel.objects.filter(slug=demo.get('grade_slug', '')).first()
    grade_band = grade_band_for_grade(grade)
    plan = SubscriptionPlan.objects.filter(
        is_active=True,
        plan_type=SubscriptionPlan.PlanType.SINGLE_TEST,
        grade_band=grade_band,
    ).first() if grade_band else None
    form = SubscribeForm(request.POST or None)

    if request.method == 'POST' and plan and form.is_valid():
        token_hash = _guest_demo_token_hash(request, create=True)
        pending_payment = GuestDemoPayment.objects.filter(
            session_token_hash=token_hash,
            demo_id=demo['demo_id'],
            status=GuestDemoPayment.Status.PENDING,
        ).exclude(checkout_request_id='').first()
        if pending_payment:
            return redirect(
                'subscriptions:guest_demo_payment_pending',
                payment_uuid=pending_payment.uuid,
            )
        payment = GuestDemoPayment.objects.create(
            session_token_hash=token_hash,
            demo_id=demo['demo_id'],
            plan=plan,
            amount_kes=plan.price_kes,
            phone_number=form.cleaned_data['phone_number'],
            status=GuestDemoPayment.Status.PENDING,
        )
        try:
            stk_response = initiate_stk_push(
                phone_number=payment.phone_number,
                amount=int(plan.price_kes),
                account_reference=str(payment.uuid)[:12],
                description='Practice exam',
            )
        except (MpesaConfigError, MpesaAPIError, ValueError) as exc:
            payment.status = GuestDemoPayment.Status.FAILED
            payment.result_description = str(exc)[:255]
            payment.save(update_fields=['status', 'result_description', 'updated_at'])
            form.add_error(None, str(exc))
        else:
            payment.merchant_request_id = stk_response.get('MerchantRequestID', '')
            payment.checkout_request_id = stk_response.get('CheckoutRequestID', '')
            payment.save(update_fields=[
                'merchant_request_id', 'checkout_request_id', 'updated_at',
            ])
            return redirect(
                'subscriptions:guest_demo_payment_pending',
                payment_uuid=payment.uuid,
            )

    question_ids = demo.get('question_ids') or []
    total_questions = len(question_ids)
    answered = len(demo.get('answers') or {})
    remaining_questions = max(0, total_questions - answered)

    return render(request, 'subscriptions/guest_demo_checkout.html', {
        'demo': demo,
        'plan': plan,
        'form': form,
        'total_questions': total_questions,
        'remaining_questions': remaining_questions,
    })


def guest_demo_payment_pending_view(request, payment_uuid):
    payment = _guest_demo_payment_for_request(request, payment_uuid)
    if not payment:
        return redirect('core:exam_take')
    return render(request, 'subscriptions/guest_demo_payment_pending.html', {
        'payment': payment,
        'plan': payment.plan,
    })


@require_GET
def guest_demo_payment_status_view(request, payment_uuid):
    payment = _guest_demo_payment_for_request(request, payment_uuid)
    if not payment:
        return JsonResponse({'status': 'not_found'}, status=404)

    if payment.status == GuestDemoPayment.Status.PENDING and payment.checkout_request_id:
        try:
            query_data = query_stk_status(payment.checkout_request_id)
            result_code = query_data.get('ResultCode')
            if str(result_code) == '0':
                _update_guest_demo_payment(payment, {
                    'result_code': 0,
                    'result_description': query_data.get('ResultDesc', 'Payment successful.'),
                })
                payment.refresh_from_db()
            elif str(result_code) == '1032':
                _update_guest_demo_payment(payment, {
                    'result_code': 1032,
                    'result_description': query_data.get('ResultDesc', 'Payment cancelled.'),
                })
                payment.refresh_from_db()
            elif result_code not in (None,) and str(result_code) != '4999':
                _update_guest_demo_payment(payment, {
                    'result_code': int(result_code) if str(result_code).isdigit() else -1,
                    'result_description': query_data.get('ResultDesc', 'Payment failed.'),
                })
                payment.refresh_from_db()
        except (MpesaConfigError, MpesaAPIError) as exc:
            logger.warning('Guest STK query failed for %s: %s', payment.uuid, exc)

    return JsonResponse({
        'status': payment.status,
        'result_description': payment.result_description,
        'mpesa_receipt_number': payment.mpesa_receipt_number,
        'redirect_url': reverse('core:exam_take') if payment.status == GuestDemoPayment.Status.SUCCESS else None,
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
    ).first() if checkout_id else None
    if not payment and merchant_id:
        payment = Payment.objects.filter(merchant_request_id=merchant_id).first()

    guest_payment = None
    if not payment:
        if checkout_id:
            guest_payment = GuestDemoPayment.objects.filter(
                checkout_request_id=checkout_id,
            ).first()
        if not guest_payment and merchant_id:
            guest_payment = GuestDemoPayment.objects.filter(
                merchant_request_id=merchant_id,
            ).first()

    if not payment and not guest_payment:
        logger.warning('M-Pesa callback for unknown payment: %s', checkout_id)
        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Accepted'})

    if guest_payment:
        _update_guest_demo_payment(
            guest_payment,
            parsed,
            callback_payload=payload,
        )
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
    """Admin: paginated ledger of guardian subscription + guest exam M-Pesa payments."""
    denied = _admin_access_or_redirect(request)
    if denied:
        return denied

    search = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    valid_statuses = {choice[0] for choice in Payment.Status.choices}
    if status and status not in valid_statuses:
        status = ''

    page_obj = Paginator(
        _build_admin_payment_ledger(search=search, status=status),
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

    filters = _parse_admin_subscription_list_filters(request)
    page_obj = Paginator(
        _get_admin_subscriptions_queryset(**filters),
        ADMIN_SUBSCRIPTIONS_PAGE_SIZE,
    ).get_page(request.GET.get('page'))

    return render(request, 'accounts/admin_subscriptions_list.html', {
        'page_obj': page_obj,
        'search': filters['search'],
        'status_filter': filters['status'],
        'filter_plan': filters['plan'],
        'filter_live': filters['live'],
        'filter_plan_type': filters['plan_type'],
        'filter_credits': filters['credits'],
        'filter_scope': filters['scope'],
        'has_filters': _admin_subscription_list_has_filters(filters),
        'status_choices': Subscription.Status.choices,
        'plan_choices': _admin_subscription_plan_choices(),
        'plan_type_choices': SubscriptionPlan.PlanType.choices,
        'stats': _build_admin_subscription_stats(),
        'pagination_extra': _pagination_extra_params(request, ['page']),
        'django_admin_url': reverse('admin:subscriptions_subscription_changelist'),
    })
