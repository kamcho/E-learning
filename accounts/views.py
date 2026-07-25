import json

from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login as auth_login, logout as auth_logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models import Avg, Count, Max, Q
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta

ATTEMPTS_PAGE_SIZE = 10
ADMIN_LIST_PAGE_SIZE = 15

from .auth_utils import user_needs_phone_link
from .forms import SignUpForm, SignInForm, StudentForm, CompleteProfileForm
from .google_auth import GoogleAuthError, get_or_create_user_from_google, verify_google_credential
from .models import LinkedStudents, Student, MyUser, Role
from .ratelimit import throttle_google_auth, throttle_login_attempt


def _resolve_post_login_redirect(request, user, next_url=None):
    """Return a safe post-login redirect path for the given user."""
    next_url = next_url or request.GET.get('next') or request.POST.get('next')

    if user_needs_phone_link(user):
        profile_url = reverse('accounts:complete_profile')
        if next_url and next_url != 'core:landing' and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return f'{profile_url}?{urlencode({"next": next_url})}'
        return profile_url

    if next_url and next_url != 'core:landing' and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    if user.is_admin_role:
        return reverse('accounts:admin_dashboard')
    if user.is_guardian:
        return reverse('accounts:guardian_dashboard')
    if user.is_referral:
        return reverse('accounts:referral_dashboard')
    if user.is_teacher:
        return reverse('accounts:teacher_dashboard')
    if user.is_staff:
        return reverse('accounts:admin_dashboard')
    return reverse('core:landing')


def _auth_page_context(**extra):
    client_id = ''
    ids = getattr(settings, 'GOOGLE_CLIENT_IDS', None) or []
    if ids:
        client_id = ids[0]
    else:
        client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '') or ''
    return {
        'google_client_id': client_id,
        'google_signin_enabled': bool(client_id),
        **extra,
    }

def signup_view(request):
    """View to handle user registration (Sign Up)."""
    from .referrals import (
        apply_referral_to_user,
        pop_referral_code_from_session,
        resolve_referrer,
        store_referral_code_in_session,
    )

    if request.user.is_authenticated:
        return redirect('core:landing')

    next_url = request.GET.get('next', '')
    ref_from_query = request.GET.get('ref', '').strip()
    if ref_from_query:
        store_referral_code_in_session(request, ref_from_query)

    referral_code = (
        request.POST.get('referral_code', '').strip().upper()
        or request.session.get('referral_code', '').strip().upper()
    )
    referral_agent = resolve_referrer(referral_code) if referral_code else None

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            ref_code = form.cleaned_data.get('referral_code') or pop_referral_code_from_session(request)
            if ref_code:
                apply_referral_to_user(user, ref_code)
            # Automatically authenticate and log in the user
            raw_pin = form.cleaned_data.get('password')
            authenticated_user = authenticate(
                request, 
                phone=user.phone, 
                password=raw_pin
            )
            if authenticated_user:
                auth_login(request, authenticated_user)
                messages.success(request, f"Welcome to Soma Smart, {user.first_name}! Your account has been created.")
                return redirect(_resolve_post_login_redirect(request, authenticated_user))
            else:
                messages.warning(request, "Registration successful. Please log in.")
                return redirect('accounts:signin')
        else:
            messages.error(request, "Please correct the errors in the signup form.")
    else:
        form = SignUpForm(initial={'referral_code': referral_code} if referral_code else None)

    return render(request, 'accounts/signup.html', _auth_page_context(
        form=form,
        next=next_url,
        referral_code=referral_code,
        referral_agent=referral_agent,
    ))

def signin_view(request):
    """View to handle user authentication (Sign In)."""
    from .referrals import store_referral_code_in_session

    if request.user.is_authenticated:
        return redirect(_resolve_post_login_redirect(request, request.user))

    ref_from_query = request.GET.get('ref', '').strip()
    if ref_from_query:
        store_referral_code_in_session(request, ref_from_query)
        
    next_url = request.GET.get('next', 'core:landing')
    
    if request.method == 'POST':
        phone = (request.POST.get('phone') or '').strip()
        throttle_msg = throttle_login_attempt(request, phone)
        if throttle_msg:
            messages.error(request, throttle_msg)
            form = SignInForm(request.POST)
            return render(request, 'accounts/signin.html', _auth_page_context(form=form, next=next_url))

        form = SignInForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data.get('phone')
            password = form.cleaned_data.get('password')

            user = authenticate(request, phone=phone, password=password)
            if user is not None:
                auth_login(request, user)
                messages.success(request, f"Welcome back, {user.first_name}!")
                return redirect(_resolve_post_login_redirect(request, user, next_url))
            else:
                messages.error(request, "Invalid phone number or PIN. Please try again.")
        else:
            messages.error(request, "Please enter both phone number and PIN.")
    else:
        form = SignInForm()
        
    return render(request, 'accounts/signin.html', _auth_page_context(form=form, next=next_url))


@require_POST
def google_auth_view(request):
    """Verify a Google ID token and sign the user in."""
    if request.user.is_authenticated:
        return JsonResponse({
            'ok': True,
            'redirect': _resolve_post_login_redirect(request, request.user),
        })

    throttle_msg = throttle_google_auth(request)
    if throttle_msg:
        return JsonResponse({'ok': False, 'error': throttle_msg}, status=429)

    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid request payload.'}, status=400)

    credential = payload.get('credential') or request.POST.get('credential')
    if not credential:
        return JsonResponse({'ok': False, 'error': 'Missing Google credential.'}, status=400)

    try:
        idinfo = verify_google_credential(credential)
        user, created = get_or_create_user_from_google(idinfo)
    except GoogleAuthError as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

    if created:
        from .referrals import apply_referral_to_user, pop_referral_code_from_session
        ref_code = pop_referral_code_from_session(request)
        if ref_code:
            apply_referral_to_user(user, ref_code)

    if not user.is_active:
        return JsonResponse({'ok': False, 'error': 'This account is inactive.'}, status=403)

    auth_login(
        request,
        user,
        backend='django.contrib.auth.backends.ModelBackend',
    )
    if created:
        messages.success(request, f"Welcome to Soma Smart, {user.first_name}!")
    else:
        messages.success(request, f"Welcome back, {user.first_name}!")

    return JsonResponse({
        'ok': True,
        'redirect': _resolve_post_login_redirect(request, user, payload.get('next')),
    })


@login_required(login_url='accounts:signin')
def complete_profile_view(request):
    """Link phone + PIN after Google sign-in for backup login."""
    from django.contrib.auth import update_session_auth_hash

    if not user_needs_phone_link(request.user):
        return redirect(_resolve_post_login_redirect(request, request.user))

    next_url = request.GET.get('next', '')

    if request.method == 'POST':
        form = CompleteProfileForm(request.POST, user=request.user)
        if form.is_valid():
            user = request.user
            user.phone = form.cleaned_data['phone']
            user.set_password(form.cleaned_data['password'])
            user.save(update_fields=['phone', 'password'])
            # Keep the Google session alive after setting a PIN hash.
            update_session_auth_hash(request, user)
            messages.success(
                request,
                'Your phone number is linked. You can sign in with Google or your PIN anytime.',
            )
            return redirect(
                _resolve_post_login_redirect(
                    request,
                    user,
                    request.POST.get('next') or next_url,
                )
            )
    else:
        form = CompleteProfileForm(user=request.user)

    return render(request, 'accounts/complete_profile.html', {
        'form': form,
        'next': next_url,
        'user': request.user,
    })


def signout_view(request):
    """View to handle log out."""
    auth_logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('core:landing')


def _get_guardian_students(user):
    """Return all learners linked to a guardian account."""
    students = []
    for link in user.linked_students.prefetch_related('students__grade_level'):
        students.extend(link.students.all())
    return students


def _student_attempts_qs(student):
    from core.models import UserAttempts

    return (
        UserAttempts.objects
        .filter(student=student, is_active=True)
        .select_related('quiz', 'quiz__subject', 'quiz__strand')
        .prefetch_related('quiz__questions', 'responses')
        .order_by('-updated_at')
    )


def _build_attempt_course_row(attempt, student):
    quiz = attempt.quiz
    question_count = quiz.questions.filter(is_active=True).count()
    answered_count = attempt.responses.count()
    if attempt.is_complete:
        progress = 100
        status = 'completed'
        status_label = 'Completed'
    elif answered_count and question_count:
        progress = min(99, round((answered_count / question_count) * 100))
        status = 'ongoing'
        status_label = 'Ongoing'
    else:
        progress = 0
        status = 'ongoing'
        status_label = 'Ongoing'

    if attempt.marks_possible:
        score_display = f'{attempt.marks_earned}/{attempt.marks_possible} ({attempt.score}%)'
    elif attempt.is_complete:
        score_display = f'{attempt.score}%'
    else:
        score_display = '—'

    return {
        'attempt': attempt,
        'title': quiz.title,
        'subject': quiz.subject.name if quiz.subject_id else 'General',
        'strand': quiz.strand.name if quiz.strand_id else '—',
        'difficulty': quiz.difficulty,
        'question_count': question_count,
        'progress': progress,
        'status': status,
        'status_label': status_label,
        'score_display': score_display,
        'score_percent': attempt.score if attempt.is_complete else None,
        'attempt_date': attempt.created_at,
        'detail_url': reverse(
            'core:attempt_detail',
            kwargs={'quiz_uuid': quiz.uuid, 'student_uuid': student.uuid},
        ) if attempt.is_complete else reverse(
            'core:test_info',
            kwargs={'quiz_uuid': quiz.uuid, 'student_uuid': student.uuid},
        ),
    }


def _paginate_attempt_courses(student, page_number, status='all'):
    from .dashboard_filters import filter_attempts_by_status

    qs = filter_attempts_by_status(_student_attempts_qs(student), status)
    paginator = Paginator(qs, ATTEMPTS_PAGE_SIZE)
    page = paginator.get_page(page_number)
    courses = [_build_attempt_course_row(attempt, student) for attempt in page.object_list]
    return page, courses


def _build_learner_dashboard_data(student, filters=None):
    """Build student-detail dashboard metrics from quiz attempts."""
    from .dashboard_filters import (
        build_activity_chart,
        build_performance_summary,
        chart_days_for_filters,
        parse_dashboard_filters,
    )

    if filters is None:
        filters = parse_dashboard_filters(type('R', (), {'GET': {}})())

    attempts_qs = _student_attempts_qs(student)

    activity = build_activity_chart(attempts_qs, filters)
    performance = build_performance_summary(attempts_qs, filters)

    first_attempt = attempts_qs.order_by('created_at').first()
    enrolled_on = first_attempt.created_at if first_attempt else None

    from achievements.services import build_achievements_context, evaluate_student_achievements

    evaluate_student_achievements(student)
    achievements = build_achievements_context(student)

    chart_days = chart_days_for_filters(filters)
    chart_range = None
    if filters.get('month'):
        from .dashboard_filters import month_date_range
        chart_range = month_date_range(filters['month'])

    return {
        'weekly_bars': activity['weekly_bars'],
        'max_bar': activity['max_bar'],
        'week_total': activity['week_total'],
        'subject_activity': activity['subject_activity'],
        'activity_period_label': activity['period_label'],
        'performance_breakdown': performance['performance_breakdown'],
        'performance_period_label': performance['period_label'],
        'performance_avg_score': performance['avg_score'],
        'enrolled_on': enrolled_on,
        'achievements': achievements,
        'attempt_chart': _build_attempt_score_chart(
            days=chart_days,
            student=student,
            date_range=chart_range,
        ),
    }


@login_required(login_url='accounts:signin')
def guardian_dashboard_view(request):
    """
    Guardian dashboard styled as a student-details view for the selected learner.
    """
    user = request.user
    if not user.is_guardian:
        messages.error(request, "The guardian dashboard is only available to guardian accounts.")
        return redirect('core:landing')

    students = _get_guardian_students(user)
    active_student = None
    student_uuid = request.GET.get('student', '').strip()
    if students and student_uuid:
        active_student = next(
            (student for student in students if str(student.uuid) == student_uuid),
            None,
        )

    require_learner_selection = bool(students) and active_student is None

    student_index = 0
    if active_student:
        for index, student in enumerate(students, start=1):
            if student.uuid == active_student.uuid:
                student_index = index
                break

    grade_slug = request.GET.get('grade', '').strip() or None
    attempts_page_number = request.GET.get('attempts_page', '1')

    from .dashboard_filters import (
        ACTIVITY_PERIOD_CHOICES,
        ANALYTICS_PERIOD_CHOICES,
        CHART_PERIOD_CHOICES,
        PERFORMANCE_PERIOD_CHOICES,
        STATUS_CHOICES,
        build_dashboard_query_params,
        parse_dashboard_filters,
    )
    from urllib.parse import urlencode

    dashboard_filters = parse_dashboard_filters(request)

    if active_student:
        dashboard = _build_learner_dashboard_data(active_student, filters=dashboard_filters)
        analytics_ctx = _build_student_analytics_context(
            active_student,
            grade_slug=dashboard_filters.get('grade') or grade_slug,
            filters=dashboard_filters,
        )
        attempts_page, attempt_courses = _paginate_attempt_courses(
            active_student,
            attempts_page_number,
            status=dashboard_filters['status'],
        )
        dashboard_query = urlencode(
            build_dashboard_query_params(dashboard_filters, active_student.uuid)
        )
    else:
        dashboard = {
            'analytics': {
                'total_attempts': 0,
                'completed': 0,
                'completion_rate': 0,
                'avg_score': 0,
                'best_score': 0,
            },
            'weekly_bars': [],
            'max_bar': 1,
            'week_total': 0,
            'subject_activity': [],
            'performance_breakdown': [],
            'enrolled_on': None,
            'achievements': {'earned': [], 'locked': [], 'earned_count': 0, 'total_count': 0},
            'attempt_chart': _build_attempt_score_chart(),
        }
        analytics_ctx = {}
        attempts_page = None
        attempt_courses = []
        dashboard_query = ''

    context = {
        'guardian': user,
        'students': students,
        'student_count': len(students),
        'active_student': active_student,
        'student': active_student,
        'student_code': f'STU-{student_index:03d}' if active_student else '',
        'dashboard': dashboard,
        'analytics': analytics_ctx.get('analytics', dashboard.get('analytics', {})),
        'subject_breakdown': analytics_ctx.get('subject_breakdown', []),
        'selected_grade': analytics_ctx.get('selected_grade'),
        'grade_filter_options': analytics_ctx.get('grade_filter_options', []),
        'difficulty_breakdown': analytics_ctx.get('difficulty_breakdown', []),
        'subject_score_chart': analytics_ctx.get('subject_score_chart'),
        'recent_attempts': analytics_ctx.get('recent_attempts', []),
        'preserve_student_in_grade_filter': True,
        'grade_filter_action': reverse('accounts:guardian_dashboard'),
        'attempts_page': attempts_page,
        'attempt_courses': attempt_courses,
        'achievements': dashboard.get('achievements'),
        'pathway_suggestions': analytics_ctx.get('pathway_suggestions'),
        'require_learner_selection': require_learner_selection,
        'dashboard_filters': dashboard_filters,
        'dashboard_query': dashboard_query,
        'dashboard_hidden_params': build_dashboard_query_params(
            dashboard_filters,
            active_student.uuid if active_student else None,
        ),
        'activity_period_choices': ACTIVITY_PERIOD_CHOICES,
        'performance_period_choices': PERFORMANCE_PERIOD_CHOICES,
        'chart_period_choices': CHART_PERIOD_CHOICES,
        'analytics_period_choices': ANALYTICS_PERIOD_CHOICES,
        'status_choices': STATUS_CHOICES,
        'analytics_period_label': analytics_ctx.get('analytics_period_label', ''),
    }
    return render(request, 'accounts/guardian_dashboard.html', context)


@login_required(login_url='accounts:signin')
def referral_dashboard_view(request):
    """Dashboard for referral agents — share link, track signups and points."""
    from .referrals import build_referral_dashboard_context

    user = request.user
    if not user.is_referral:
        messages.error(request, 'The referral dashboard is only available to referral agents.')
        return redirect('core:landing')

    context = build_referral_dashboard_context(user, request)
    context['agent'] = user
    return render(request, 'accounts/referral_dashboard.html', context)


@login_required(login_url='accounts:signin')
def add_learner_view(request):
    """Allow a guardian to create a new learner and link them to their account."""
    user = request.user
    if not user.is_guardian:
        messages.error(request, "Only guardian accounts can add learners.")
        return redirect('core:landing')

    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            student = form.save()
            link, _ = LinkedStudents.objects.get_or_create(user=user)
            link.students.add(student)
            messages.success(
                request,
                f"{student.first_name} {student.last_name} has been added and linked to your account.",
            )
            return redirect(
                f"{reverse('accounts:guardian_dashboard')}?{urlencode({'student': str(student.uuid)})}"
            )
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = StudentForm()

    return render(request, 'accounts/add_learner.html', {'form': form})


def _is_admin(user):
    return user.is_admin_role or user.is_staff


def _admin_access_or_redirect(request):
    if not _is_admin(request.user):
        messages.error(request, "You don't have permission to view this page.")
        return redirect('core:landing')
    return None


def _teacher_access_or_redirect(request):
    if not request.user.is_teacher:
        messages.error(request, "The teacher dashboard is only available to teacher accounts.")
        return redirect('core:landing')
    return None


def _pagination_extra_params(request, exclude_keys):
    params = request.GET.copy()
    for key in exclude_keys:
        params.pop(key, None)
    return params.urlencode()


def _get_admin_users_queryset(search=''):
    qs = MyUser.objects.order_by('-date_joined')
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
            | Q(role__icontains=search)
        )
    return qs


def _get_admin_students_queryset(search=''):
    qs = Student.objects.select_related('grade_level').order_by('first_name', 'last_name')
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(gender__icontains=search)
            | Q(grade_level__name__icontains=search)
        )
    return qs


def _build_admin_user_stats():
    users_by_role = {
        role.value: MyUser.objects.filter(role=role.value).count()
        for role in Role
    }
    return {
        'total': MyUser.objects.count(),
        'active': MyUser.objects.filter(is_active=True).count(),
        'inactive': MyUser.objects.filter(is_active=False).count(),
        'guardians': users_by_role.get(Role.GUARDIAN.value, 0),
        'teachers': users_by_role.get(Role.TEACHER.value, 0),
        'admins': users_by_role.get(Role.ADMIN.value, 0),
    }


def _build_admin_student_stats():
    total = Student.objects.count()
    graded = Student.objects.filter(grade_level__isnull=False).count()
    return {
        'total': total,
        'male': Student.objects.filter(gender='Male').count(),
        'female': Student.objects.filter(gender='Female').count(),
        'graded': graded,
        'ungraded': total - graded,
        'linked': Student.objects.filter(linked_students__isnull=False).distinct().count(),
    }


def _build_attempt_score_chart(days=7, student=None, date_range=None):
    """Daily average & best scores from attempts (optionally for one learner)."""
    from core.models import UserAttempts

    today = timezone.localdate()
    if date_range:
        start, end = date_range
        days = (end - start).days + 1
    else:
        start = today - timedelta(days=days - 1)
        end = today

    prev_days = days
    prev_start = start - timedelta(days=prev_days)
    prev_end = start - timedelta(days=1)

    attempts_qs = UserAttempts.objects.filter(is_active=True)
    if student is not None:
        attempts_qs = attempts_qs.filter(student=student)

    daily_stats = {
        row['day']: row
        for row in (
            attempts_qs
            .filter(created_at__date__gte=start, created_at__date__lte=end)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(
                avg_score=Avg('score'),
                best_score=Max('score'),
                count=Count('uuid'),
            )
        )
    }

    labels, avg_scores, best_scores, counts = [], [], [], []
    span = (end - start).days + 1
    use_weekly = span > 31

    if use_weekly:
        cursor = start
        while cursor <= end:
            bucket_end = min(cursor + timedelta(days=6), end)
            bucket_attempts = attempts_qs.filter(
                created_at__date__gte=cursor,
                created_at__date__lte=bucket_end,
            )
            agg = bucket_attempts.aggregate(
                avg_score=Avg('score'),
                best_score=Max('score'),
                count=Count('uuid'),
            )
            labels.append(cursor.strftime('%d %b'))
            avg_scores.append(round(agg['avg_score'] or 0, 1))
            best_scores.append(agg['best_score'] or 0)
            counts.append(agg['count'] or 0)
            cursor = bucket_end + timedelta(days=1)
    else:
        for i in range(span):
            d = start + timedelta(days=i)
            labels.append(d.strftime('%a') if span <= 14 else d.strftime('%d %b'))
            row = daily_stats.get(d)
            if row:
                avg_scores.append(round(row['avg_score'] or 0, 1))
                best_scores.append(row['best_score'] or 0)
                counts.append(row['count'])
            else:
                avg_scores.append(0)
                best_scores.append(0)
                counts.append(0)

    current_avg = attempts_qs.filter(
        created_at__date__gte=start,
        created_at__date__lte=end,
    ).aggregate(v=Avg('score'))['v'] or 0
    prev_avg = attempts_qs.filter(
        created_at__date__gte=prev_start,
        created_at__date__lte=prev_end,
    ).aggregate(v=Avg('score'))['v'] or 0

    if prev_avg:
        trend_pct = round(((current_avg - prev_avg) / prev_avg) * 100, 1)
    elif current_avg:
        trend_pct = 100.0
    else:
        trend_pct = 0.0

    return {
        'labels': labels,
        'avg_scores': avg_scores,
        'best_scores': best_scores,
        'counts': counts,
        'trend_pct': abs(trend_pct),
        'trend_up': trend_pct >= 0,
        'period_label': f'{start.strftime("%b %d")} – {end.strftime("%b %d, %Y")}',
    }


GRADE_SLUG_ORDER = [
    'pp1', 'pp2',
    'grade-1', 'grade-2', 'grade-3', 'grade-4', 'grade-5', 'grade-6',
    'grade-7', 'grade-8', 'grade-9', 'grade-10', 'grade-11', 'grade-12',
]


def _grade_sort_key(grade):
    try:
        return GRADE_SLUG_ORDER.index(grade.slug)
    except ValueError:
        return 999


def _get_grade_filter_options(student):
    """Grades the learner can view: current grade and all previous grades."""
    from subjects.models import GradeLevel

    all_grades = sorted(GradeLevel.objects.all(), key=_grade_sort_key)
    if not student.grade_level_id:
        return all_grades

    student_index = _grade_sort_key(student.grade_level)
    return [grade for grade in all_grades if _grade_sort_key(grade) <= student_index]


def _resolve_subject_grade_filter(student, grade_slug):
    """Pick the grade for the subject breakdown (defaults to learner's grade)."""
    from subjects.models import GradeLevel

    options = _get_grade_filter_options(student)
    if not options:
        return None, options

    by_slug = {grade.slug: grade for grade in options}
    if grade_slug and grade_slug in by_slug:
        return by_slug[grade_slug], options

    if student.grade_level_id:
        for grade in options:
            if grade.pk == student.grade_level_id:
                return grade, options

    return options[-1], options


def _build_grade_subject_breakdown(attempts_qs, grade_level):
    """List every subject in a grade with attempt stats (0 when none)."""
    from subjects.models import Subject

    if not grade_level:
        return []

    grade_attempts = attempts_qs.filter(
        quiz__subject__grade_level_id=grade_level.pk,
        quiz__subject__isnull=False,
    )

    stats_by_subject = {
        row['quiz__subject_id']: row
        for row in grade_attempts
        .values('quiz__subject_id', 'quiz__subject__name')
        .annotate(attempts=Count('uuid'), avg_score=Avg('score'), best_score=Max('score'))
    }

    breakdown = []
    for subject in Subject.objects.filter(
        grade_level=grade_level,
        is_active=True,
    ).order_by('name'):
        stats = stats_by_subject.get(subject.pk)
        breakdown.append({
            'subject_id': subject.pk,
            'quiz__subject__name': subject.name,
            'attempts': stats['attempts'] if stats else 0,
            'avg_score': stats['avg_score'] if stats and stats['avg_score'] is not None else 0,
            'best_score': stats['best_score'] if stats else 0,
        })

    breakdown.sort(key=lambda row: (-row['avg_score'], row['quiz__subject__name']))
    return breakdown


def _build_difficulty_breakdown(attempts_qs):
    """Fixed Easy / Medium / Hard tiles regardless of attempt count."""
    rows = {
        row['quiz__difficulty']: row
        for row in (
            attempts_qs
            .values('quiz__difficulty')
            .annotate(attempts=Count('uuid'), avg_score=Avg('score'))
        )
    }
    breakdown = []
    for level in ('Easy', 'Medium', 'Hard'):
        row = rows.get(level)
        breakdown.append({
            'quiz__difficulty': level,
            'attempts': row['attempts'] if row else 0,
            'avg_score': row['avg_score'] if row and row['avg_score'] is not None else 0,
        })
    return breakdown


def _build_subject_score_chart(subject_breakdown, selected_grade):
    """Chart data: avg & best score per subject in the selected grade."""
    rows = sorted(subject_breakdown, key=lambda row: row['quiz__subject__name'])
    return {
        'labels': [row['quiz__subject__name'] for row in rows],
        'avg_scores': [round(row['avg_score'] or 0, 1) for row in rows],
        'best_scores': [row['best_score'] or 0 for row in rows],
        'counts': [row['attempts'] for row in rows],
        'period_label': selected_grade.name if selected_grade else 'No grade assigned',
    }


def _build_student_analytics_context(student, grade_slug=None, filters=None):
    """Shared analytics context for guardian and admin student views."""
    from core.models import UserAttempts

    from .dashboard_filters import (
        build_analytics_summary,
        chart_days_for_filters,
        parse_dashboard_filters,
    )

    if filters is None:
        filters = parse_dashboard_filters(type('R', (), {'GET': {}})())

    base_qs = (
        UserAttempts.objects
        .filter(student=student, is_active=True)
        .select_related('quiz', 'quiz__subject', 'quiz__strand', 'quiz__sub_strand')
    )

    analytics_summary = build_analytics_summary(base_qs, filters)
    attempts_qs = analytics_summary.pop('attempts_qs')
    period_label = analytics_summary.pop('period_label')

    selected_grade, grade_filter_options = _resolve_subject_grade_filter(student, grade_slug)
    subject_breakdown = _build_grade_subject_breakdown(attempts_qs, selected_grade)
    difficulty_breakdown = _build_difficulty_breakdown(attempts_qs)
    subject_score_chart = _build_subject_score_chart(subject_breakdown, selected_grade)
    subject_score_chart['period_label'] = (
        f'{selected_grade.name} · {period_label}' if selected_grade else period_label
    )

    from achievements.services import build_achievements_context, evaluate_student_achievements

    evaluate_student_achievements(student)
    achievements = build_achievements_context(student)

    from .pathway_suggestions import build_pathway_suggestions

    pathway_suggestions = build_pathway_suggestions(student, grade_level=selected_grade)

    chart_days = chart_days_for_filters(filters)
    chart_range = None
    if filters.get('month'):
        from .dashboard_filters import month_date_range
        chart_range = month_date_range(filters['month'])

    return {
        'student': student,
        'analytics': analytics_summary,
        'analytics_period_label': period_label,
        'subject_breakdown': subject_breakdown,
        'selected_grade': selected_grade,
        'grade_filter_options': grade_filter_options,
        'difficulty_breakdown': difficulty_breakdown,
        'subject_score_chart': subject_score_chart,
        'recent_attempts': attempts_qs.order_by('-created_at')[:10],
        'attempt_chart': _build_attempt_score_chart(
            days=chart_days,
            student=student,
            date_range=chart_range,
        ),
        'achievements': achievements,
        'pathway_suggestions': pathway_suggestions,
    }


@login_required(login_url='accounts:signin')
def student_subject_progress_view(request, student_uuid, subject_id):
    """Strand and sub-strand test progress for a learner in one subject."""
    from subjects.models import Subject

    from .progress import build_subject_strand_progress

    student = get_object_or_404(Student.objects.select_related('grade_level'), uuid=student_uuid)
    subject = get_object_or_404(
        Subject.objects.select_related('grade_level', 'discipline'),
        pk=subject_id,
        is_active=True,
    )

    if not _is_admin(request.user):
        is_linked = request.user.linked_students.filter(students=student).exists()
        if not is_linked:
            messages.error(request, "You don't have permission to view this learner's progress.")
            return redirect('accounts:guardian_dashboard')

    progress = build_subject_strand_progress(student, subject)
    if _is_admin(request.user):
        back_url = reverse('accounts:student_analytics', kwargs={'student_uuid': student.uuid})
    else:
        back_url = f"{reverse('accounts:guardian_dashboard')}?{urlencode({'student': str(student.uuid)})}"
    context = {
        'student': student,
        'subject': subject,
        'progress': progress,
        'back_url': back_url,
    }
    return render(request, 'accounts/student_subject_progress.html', context)


@login_required(login_url='accounts:signin')
def student_analytics_view(request, student_uuid):
    """
    Detailed analytics for a student.
    Guardians may only view linked students; admins may view any student.
    """
    student = get_object_or_404(Student.objects.select_related('grade_level'), uuid=student_uuid)

    grade_slug = request.GET.get('grade', '').strip() or None

    if _is_admin(request.user):
        context = _build_student_analytics_context(student, grade_slug=grade_slug)
        return render(request, 'accounts/admin_student_analytics.html', context)

    is_linked = request.user.linked_students.filter(students=student).exists()
    if not is_linked:
        messages.error(request, "You don't have permission to view this student's analytics.")
        return redirect('accounts:guardian_dashboard')

    params = {'student': str(student.uuid)}
    if grade_slug:
        params['grade'] = grade_slug
    return redirect(f"{reverse('accounts:guardian_dashboard')}?{urlencode(params)}")


@login_required(login_url='accounts:signin')
def admin_dashboard_view(request):
    """
    Platform admin dashboard: user/student stats, curriculum counts,
    and quick links to manage all related models in Django admin.
    """
    from core.models import Quiz, Question, UserAttempts
    from subjects.models import (
        GradeLevel, Discipline, Subject, Strand, SubStrand,
        StrandObjective, SubStrandObjective,
    )

    user = request.user
    if not _is_admin(user):
        messages.error(request, "The admin dashboard is only available to admin accounts.")
        return redirect('core:landing')

    users_by_role = {
        role.value: MyUser.objects.filter(role=role.value).count()
        for role in Role
    }
    total_users = MyUser.objects.count()
    active_users = MyUser.objects.filter(is_active=True).count()
    total_students = Student.objects.count()
    linked_student_links = LinkedStudents.objects.count()

    curriculum_counts = {
        'grade_levels': GradeLevel.objects.count(),
        'disciplines': Discipline.objects.count(),
        'subjects': Subject.objects.filter(is_active=True).count(),
        'strands': Strand.objects.filter(is_active=True).count(),
        'sub_strands': SubStrand.objects.filter(is_active=True).count(),
        'strand_objectives': StrandObjective.objects.filter(is_active=True).count(),
        'sub_strand_objectives': SubStrandObjective.objects.filter(is_active=True).count(),
    }

    content_counts = {
        'quizzes': Quiz.objects.filter(is_active=True).count(),
        'questions': Question.objects.filter(is_active=True).count(),
        'attempts': UserAttempts.objects.filter(is_active=True).count(),
        'completed_attempts': UserAttempts.objects.filter(is_active=True, is_complete=True).count(),
    }

    users_paginator = Paginator(_get_admin_users_queryset(), ADMIN_LIST_PAGE_SIZE)
    students_paginator = Paginator(_get_admin_students_queryset(), ADMIN_LIST_PAGE_SIZE)
    users_page = users_paginator.get_page(request.GET.get('users_page'))
    students_page = students_paginator.get_page(request.GET.get('students_page'))
    attempt_chart = _build_attempt_score_chart()

    context = {
        'admin_user': user,
        'user_stats': {
            'total': total_users,
            'active': active_users,
            'guardians': users_by_role.get(Role.GUARDIAN.value, 0),
            'teachers': users_by_role.get(Role.TEACHER.value, 0),
            'partners': users_by_role.get(Role.PARTNER.value, 0),
            'referrals': users_by_role.get(Role.REFERRAL.value, 0),
            'admins': users_by_role.get(Role.ADMIN.value, 0),
        },
        'student_stats': {
            'total': total_students,
            'linked': linked_student_links,
        },
        'curriculum_counts': curriculum_counts,
        'curriculum_max': max(
            curriculum_counts['grade_levels'],
            curriculum_counts['disciplines'],
            curriculum_counts['subjects'],
            curriculum_counts['strands'],
            curriculum_counts['sub_strands'],
            1,
        ),
        'activity_max': max(
            total_users,
            active_users,
            total_students,
            content_counts['quizzes'],
            content_counts['attempts'],
            1,
        ),
        'content_counts': content_counts,
        'users_page': users_page,
        'students_page': students_page,
        'users_pagination_extra': _pagination_extra_params(request, ['users_page']),
        'students_pagination_extra': _pagination_extra_params(request, ['students_page']),
        'attempt_chart': attempt_chart,
        'django_admin_url': reverse('admin:index'),
        'curriculum_urls': {
            'grade_levels': reverse('subjects:grade_level_list'),
            'disciplines': reverse('subjects:discipline_list'),
            'subjects': reverse('subjects:subject_list'),
        },
    }
    return render(request, 'accounts/admin_dashboard.html', context)


@login_required(login_url='accounts:signin')
def admin_users_list_view(request):
    """Paginated list of all platform users."""
    denied = _admin_access_or_redirect(request)
    if denied:
        return denied

    search = request.GET.get('q', '').strip()
    page_obj = Paginator(
        _get_admin_users_queryset(search),
        ADMIN_LIST_PAGE_SIZE,
    ).get_page(request.GET.get('page'))

    return render(request, 'accounts/admin_users_list.html', {
        'page_obj': page_obj,
        'search': search,
        'stats': _build_admin_user_stats(),
        'pagination_extra': _pagination_extra_params(request, ['page']),
        'django_admin_url': reverse('admin:accounts_myuser_changelist'),
    })


@login_required(login_url='accounts:signin')
def admin_students_list_view(request):
    """Paginated list of all learners."""
    denied = _admin_access_or_redirect(request)
    if denied:
        return denied

    search = request.GET.get('q', '').strip()
    page_obj = Paginator(
        _get_admin_students_queryset(search),
        ADMIN_LIST_PAGE_SIZE,
    ).get_page(request.GET.get('page'))

    return render(request, 'accounts/admin_students_list.html', {
        'page_obj': page_obj,
        'search': search,
        'stats': _build_admin_student_stats(),
        'pagination_extra': _pagination_extra_params(request, ['page']),
        'django_admin_url': reverse('admin:accounts_student_changelist'),
    })


@login_required(login_url='accounts:signin')
def admin_user_detail_view(request, user_id):
    """Admin view of a single platform user."""
    from core.models import UserAttempts

    if not _is_admin(request.user):
        messages.error(request, "You don't have permission to view this page.")
        return redirect('core:landing')

    profile_user = get_object_or_404(MyUser, pk=user_id)

    linked_students = []
    for link in profile_user.linked_students.prefetch_related('students__grade_level'):
        linked_students.extend(link.students.all())

    attempts_qs = (
        UserAttempts.objects
        .filter(user=profile_user, is_active=True)
        .select_related('quiz', 'student')
    )

    summary = attempts_qs.aggregate(
        total=Count('uuid'),
        completed=Count('uuid', filter=Q(is_complete=True)),
        avg_score=Avg('score'),
    )
    total = summary['total'] or 0
    completed = summary['completed'] or 0

    context = {
        'profile_user': profile_user,
        'linked_students': linked_students,
        'analytics': {
            'total_attempts': total,
            'completed': completed,
            'avg_score': round(summary['avg_score'], 1) if summary['avg_score'] is not None else 0,
        },
        'recent_attempts': attempts_qs.order_by('-created_at')[:10],
        'django_admin_url': reverse('admin:accounts_myuser_change', args=[profile_user.pk]),
    }
    return render(request, 'accounts/admin_user_detail.html', context)


@login_required(login_url='accounts:signin')
def admin_profile_view(request):
    """Admin profile page."""
    from core.models import Quiz, UserAttempts
    from django.utils import timezone

    user = request.user
    if not _is_admin(user):
        messages.error(request, "The admin profile is only available to admin accounts.")
        return redirect('core:landing')

    days_member = (timezone.now() - user.date_joined).days
    quizzes_created = Quiz.objects.filter(created_by=user).count()
    quiz_attempts = UserAttempts.objects.filter(user=user, is_active=True).count()

    context = {
        'user': user,
        'days_member': days_member,
        'quizzes_created': quizzes_created,
        'quiz_attempts': quiz_attempts,
        'django_admin_url': reverse('admin:accounts_myuser_change', args=[user.pk]),
    }
    return render(request, 'accounts/admin_profile.html', context)


@login_required(login_url='accounts:signin')
@require_POST
def switch_role_view(request):
    """Superusers can change their own platform role in the database."""
    if not request.user.is_superuser:
        messages.error(request, 'Only superusers can switch roles.')
        return redirect('core:landing')

    from .role_utils import VALID_ROLES, redirect_path_for_role, role_label

    role = request.POST.get('role', '').strip()
    if role not in VALID_ROLES:
        messages.error(request, 'Invalid role selected.')
        return redirect(request.META.get('HTTP_REFERER', reverse('core:landing')))

    user = request.user
    if user.role != role:
        user.role = role
        user.save(update_fields=['role', 'updated_at'])
        messages.success(request, f'Your role is now {role_label(role)}.')

    return redirect(redirect_path_for_role(user))


@login_required(login_url='accounts:signin')
def teacher_dashboard_view(request):
    """Teacher overview: subjects taught, question bank, and quiz attempt analytics."""
    denied = _teacher_access_or_redirect(request)
    if denied:
        return denied

    from .teacher_analytics import (
        build_teacher_question_rows,
        build_teacher_subject_rows,
        build_teacher_summary,
    )

    teacher = request.user
    context = {
        'teacher': teacher,
        'summary': build_teacher_summary(teacher),
        'subject_rows': build_teacher_subject_rows(teacher),
        'question_rows': build_teacher_question_rows(teacher),
    }
    return render(request, 'accounts/teacher_dashboard.html', context)


@login_required(login_url='accounts:signin')
def teacher_subject_detail_view(request, subject_id):
    """Detailed analytics for one subject the teacher teaches."""
    denied = _teacher_access_or_redirect(request)
    if denied:
        return denied

    from subjects.models import Subject

    from .teacher_analytics import build_teacher_subject_detail, teacher_can_access_subject

    teacher = request.user
    subject = get_object_or_404(
        Subject.objects.select_related('grade_level', 'discipline'),
        pk=subject_id,
        is_active=True,
    )
    if not teacher_can_access_subject(teacher, subject):
        messages.error(request, "You don't have permission to view this subject.")
        return redirect('accounts:teacher_dashboard')

    detail = build_teacher_subject_detail(teacher, subject)
    context = {
        'teacher': teacher,
        'detail': detail,
        **detail,
    }
    return render(request, 'accounts/teacher_subject_detail.html', context)


@login_required(login_url='accounts:signin')
def teacher_question_detail_view(request, question_uuid):
    """Full detail for one question added by the teacher."""
    denied = _teacher_access_or_redirect(request)
    if denied:
        return denied

    from core.models import Question

    from .teacher_analytics import build_teacher_question_detail

    teacher = request.user
    question = get_object_or_404(
        Question.objects.select_related(
            'sub_strand',
            'sub_strand__strand',
            'sub_strand__strand__subject',
            'sub_strand__strand__subject__grade_level',
            'created_by',
        ).prefetch_related('options'),
        uuid=question_uuid,
        created_by=teacher,
    )
    detail = build_teacher_question_detail(teacher, question)
    context = {
        'teacher': teacher,
        'detail': detail,
        **detail,
    }
    return render(request, 'accounts/teacher_question_detail.html', context)
