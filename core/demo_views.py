import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.ratelimit import rate_limit
from core.demo import (
    DEMO_QUESTION_COUNT,
    build_demo_breakdown,
    clear_demo_session,
    finalize_demo,
    get_demo_session,
    grade_demo_answer,
    load_demo_questions,
    save_demo_session,
    select_demo_questions,
    start_demo_session,
)
from core.exam_filters import (
    active_quizzes_queryset,
    resolve_grade_from_slug,
    strands_for_wizard,
    sub_strands_for_wizard,
    subjects_for_wizard,
)
from subjects.models import GradeLevel, Strand, Subject, SubStrand


def _demo_wizard_phase(grade_chosen, subject_slug, scope, strand_slug, sub_strand_slug):
    if not grade_chosen:
        return 'grade'
    if not subject_slug:
        return 'subject'
    if not scope:
        return 'scope'
    if scope == 'general':
        return 'ready'
    if scope == 'strand' and not strand_slug:
        return 'strand'
    if scope == 'sub_strand' and not sub_strand_slug:
        return 'sub_strand'
    return 'ready'


def _build_demo_wizard_trail(*, phase, grade, subject, scope, strand, sub_strand, browse_all_grades):
    scope_labels = {
        'general': 'Whole subject',
        'strand': 'Strand focus',
        'sub_strand': 'Sub-strand focus',
    }
    steps = []
    rank = 0

    grade_value = 'All grades' if browse_all_grades else (grade.name if grade else None)
    steps.append({'key': 'grade', 'label': 'Grade', 'icon': '🏫', 'value': grade_value, 'rank': rank})
    rank += 1

    if phase != 'grade':
        steps.append({
            'key': 'subject',
            'label': 'Subject',
            'icon': '📚',
            'value': subject.name if subject else None,
            'rank': rank,
        })
        rank += 1

    if subject or phase in ('scope', 'strand', 'sub_strand', 'ready'):
        steps.append({
            'key': 'focus',
            'label': 'Test focus',
            'icon': '🎯',
            'value': scope_labels.get(scope) if scope else None,
            'rank': rank,
        })
        rank += 1

    if scope in ('strand', 'sub_strand') or strand or sub_strand:
        topic_value = sub_strand.name if sub_strand else (strand.name if strand else None)
        steps.append({
            'key': 'topic',
            'label': 'Topic',
            'icon': '🧵',
            'value': topic_value,
            'rank': rank,
        })
        rank += 1

    if phase != 'grade':
        steps.append({'key': 'tests', 'label': 'Practice test', 'icon': '✅', 'value': None, 'rank': rank})

    phase_to_key = {
        'grade': 'grade',
        'subject': 'subject',
        'scope': 'focus',
        'strand': 'topic',
        'sub_strand': 'topic',
        'ready': 'tests',
    }
    current_key = phase_to_key.get(phase, 'grade')
    current_rank = next((s['rank'] for s in steps if s['key'] == current_key), 0)

    visible = []
    for index, step in enumerate(steps, start=1):
        if step['key'] == current_key:
            state = 'current'
        elif step['rank'] < current_rank and step.get('value'):
            state = 'complete'
        elif step['key'] == 'grade' and step['rank'] < current_rank and grade_value:
            state = 'complete'
        elif step['key'] == 'subject' and step['rank'] < current_rank and subject:
            state = 'complete'
        elif step['key'] == 'focus' and step['rank'] < current_rank and scope:
            state = 'complete'
        elif step['key'] == 'topic' and step['rank'] < current_rank and (strand or sub_strand):
            state = 'complete'
        elif step['rank'] > current_rank:
            continue
        else:
            continue
        visible.append({**step, 'number': index, 'state': state})

    total = max(len(steps), 2)
    completed = sum(1 for s in visible if s['state'] == 'complete')
    current = sum(1 for s in visible if s['state'] == 'current')
    progress_pct = max(8, min(round(((completed + 0.35 * current) / total) * 100), 100))

    labels = {
        'grade': ('Choose a grade', "Select the learner's grade to see matching subjects."),
        'subject': ('Choose a subject', 'Pick a subject for your free 7-question practice test.'),
        'scope': ('Test focus', 'Whole subject, one strand, or a specific sub-strand.'),
        'strand': ('Choose a strand', 'Select the strand you want to practise.'),
        'sub_strand': ('Choose a sub-strand', 'Pick a focused sub-strand topic.'),
        'ready': ('Ready to start', f'We will build a {DEMO_QUESTION_COUNT}-question practice quiz for you.'),
    }
    current_label, current_hint = labels.get(phase, ('Continue', ''))

    return {
        'steps': visible,
        'progress_pct': progress_pct,
        'current_label': current_label,
        'current_hint': current_hint,
        'current_step_number': next((s['number'] for s in visible if s['state'] == 'current'), 1),
    }


@require_GET
def demo_wizard_view(request):
    active_demo = get_demo_session(request)
    if active_demo and not active_demo.get('completed') and request.GET.get('restart') == '1':
        clear_demo_session(request)
        active_demo = None

    if active_demo and not active_demo.get('completed') and request.GET.get('continue') == '1':
        return redirect('core:demo_take')

    grade_slug = request.GET.get('grade', '').strip()
    subject_slug = request.GET.get('subject', '').strip()
    scope = request.GET.get('scope', '').strip()
    strand_slug = request.GET.get('strand', '').strip()
    sub_strand_slug = request.GET.get('sub_strand', '').strip()

    all_grades = GradeLevel.objects.all().order_by('name')
    browse_all_grades = grade_slug == 'all'
    active_grade = None
    if browse_all_grades:
        active_grade = None
    elif grade_slug:
        active_grade = resolve_grade_from_slug(grade_slug, all_grades)

    active_subject = None
    if subject_slug:
        active_subject = Subject.objects.filter(slug=subject_slug, is_active=True).select_related('grade_level').first()
        # Deep link with subject only: inherit that subject's grade.
        if active_subject and not grade_slug:
            active_grade = active_subject.grade_level

    grade_chosen = browse_all_grades or active_grade is not None

    active_strand = None
    if strand_slug and active_subject:
        active_strand = Strand.objects.filter(slug=strand_slug, subject=active_subject, is_active=True).first()

    active_sub_strand = None
    if sub_strand_slug and active_subject:
        active_sub_strand = SubStrand.objects.filter(slug=sub_strand_slug, is_active=True).first()

    phase = _demo_wizard_phase(grade_chosen, subject_slug if grade_chosen else '', scope, strand_slug, sub_strand_slug)
    base_quizzes = active_quizzes_queryset()
    if active_grade:
        base_quizzes = base_quizzes.filter(subject__grade_level=active_grade)

    browse_subjects = []
    if grade_chosen:
        grades_for_browse = all_grades if browse_all_grades else GradeLevel.objects.filter(pk=active_grade.pk)
        for subject in Subject.objects.filter(is_active=True, grade_level__in=grades_for_browse).select_related('grade_level').order_by('grade_level__name', 'name'):
            browse_subjects.append({'subject': subject})

    browse_strands = []
    browse_sub_strands = []
    if active_subject:
        browse_strands = [{'strand': strand} for strand in strands_for_wizard(base_quizzes, subject=active_subject)]
        for strand in strands_for_wizard(base_quizzes, subject=active_subject):
            for sub in sub_strands_for_wizard(base_quizzes, strand=strand):
                browse_sub_strands.append({'sub_strand': sub, 'strand': strand})

    wizard = _build_demo_wizard_trail(
        phase=phase,
        grade=active_grade,
        subject=active_subject,
        scope=scope,
        strand=active_strand,
        sub_strand=active_sub_strand,
        browse_all_grades=browse_all_grades,
    )

    nav_grade = 'grade=all' if browse_all_grades else (f'grade={active_grade.slug}' if active_grade else '')

    return render(request, 'core/demo/wizard.html', {
        'active_demo': active_demo,
        'phase': phase,
        'demo_wizard': wizard,
        'all_grades': all_grades,
        'active_grade': active_grade,
        'browse_all_grades': browse_all_grades,
        'active_subject': active_subject,
        'active_strand': active_strand,
        'active_sub_strand': active_sub_strand,
        'active_scope': scope,
        'browse_subjects': browse_subjects,
        'browse_strands': browse_strands,
        'browse_sub_strands': browse_sub_strands,
        'nav_grade': nav_grade,
        'demo_question_count': DEMO_QUESTION_COUNT,
    })


@require_POST
def demo_start_view(request):
    grade_slug = request.POST.get('grade', '').strip()
    subject_slug = request.POST.get('subject', '').strip()
    scope = request.POST.get('scope', 'general').strip()
    strand_slug = request.POST.get('strand', '').strip()
    sub_strand_slug = request.POST.get('sub_strand', '').strip()

    all_grades = GradeLevel.objects.all()
    if grade_slug == 'all':
        messages.error(request, 'Please pick a specific grade for the demo test.')
        return redirect('core:demo_wizard')

    grade = resolve_grade_from_slug(grade_slug, all_grades) if grade_slug else None
    if not grade:
        messages.error(request, 'Please pick a grade for the demo test.')
        return redirect('core:demo_wizard')

    subject = get_object_or_404(Subject, slug=subject_slug, is_active=True, grade_level=grade)
    strand = None
    sub_strand = None
    if scope == 'strand':
        strand = get_object_or_404(Strand, slug=strand_slug, subject=subject, is_active=True)
    elif scope == 'sub_strand':
        sub_strand = get_object_or_404(SubStrand, slug=sub_strand_slug, is_active=True)
        strand = sub_strand.strand
        if strand.subject_id != subject.pk:
            messages.error(request, 'That topic does not belong to the selected subject.')
            return redirect('core:demo_wizard')

    questions = select_demo_questions(
        subject=subject,
        scope=scope,
        strand=strand,
        sub_strand=sub_strand,
    )
    if not questions:
        messages.error(
            request,
            'Not enough practice questions found for this selection. Try whole subject or another topic.',
        )
        params = f'?subject={subject.slug}&scope={scope}&grade={grade.slug}'
        if strand_slug:
            params += f'&strand={strand_slug}'
        if sub_strand_slug:
            params += f'&sub_strand={sub_strand_slug}'
        return redirect(reverse('core:demo_wizard') + params)

    demo = start_demo_session(
        grade=grade,
        subject=subject,
        scope=scope,
        strand=strand,
        sub_strand=sub_strand,
        questions=questions,
    )
    save_demo_session(request, demo)
    return redirect('core:demo_take')


@require_http_methods(['GET', 'POST'])
def demo_take_view(request):
    demo = get_demo_session(request)
    if not demo or demo.get('completed'):
        messages.info(request, 'Start a new practice test to continue.')
        return redirect('core:demo_wizard')

    questions = load_demo_questions(demo)
    if not questions:
        clear_demo_session(request)
        messages.error(request, 'This practice session expired. Please start again.')
        return redirect('core:demo_wizard')

    question_count = len(questions)
    answers = demo.get('answers', {})
    answered_count = len(answers)

    if request.method == 'POST':
        action = request.POST.get('action', 'submit')

        if action == 'continue':
            demo['feedback_index'] = None
            save_demo_session(request, demo)
            if answered_count >= question_count:
                finalize_demo(demo, questions)
                save_demo_session(request, demo)
                return redirect('core:demo_results')
            return redirect('core:demo_take')

        if answered_count >= question_count:
            finalize_demo(demo, questions)
            save_demo_session(request, demo)
            return redirect('core:demo_results')

        current_question = questions[answered_count]
        qid = str(current_question.uuid)
        if qid in answers:
            return redirect('core:demo_take')

        option_uuid = request.POST.get('answer', '').strip()
        if not option_uuid:
            messages.error(request, 'Please select an answer before submitting.')
            return redirect('core:demo_take')

        feedback = grade_demo_answer(current_question, option_uuid)
        answers[qid] = option_uuid
        demo['answers'] = answers
        demo['feedback'] = demo.get('feedback', {})
        demo['feedback'][qid] = feedback
        demo['feedback_index'] = answered_count
        save_demo_session(request, demo)
        return redirect('core:demo_take')

    feedback_index = demo.get('feedback_index')
    showing_feedback = feedback_index is not None
    if showing_feedback:
        display_index = feedback_index
    else:
        display_index = answered_count

    if display_index >= question_count:
        finalize_demo(demo, questions)
        save_demo_session(request, demo)
        return redirect('core:demo_results')

    current_question = questions[display_index]
    qid = str(current_question.uuid)
    feedback = demo.get('feedback', {}).get(qid) if showing_feedback else None
    options = list(current_question.options.filter(is_active=True).order_by('created_at'))

    nav_states = []
    for index, question in enumerate(questions):
        q_uuid = str(question.uuid)
        fb = demo.get('feedback', {}).get(q_uuid)
        if q_uuid in answers and fb:
            if fb.get('is_correct'):
                state = 'correct'
            else:
                state = 'incorrect'
        elif index == display_index:
            state = 'current'
        else:
            state = 'unanswered'
        nav_states.append(state)

    correct_count = sum(1 for fb in demo.get('feedback', {}).values() if fb.get('is_correct'))
    incorrect_count = sum(
        1 for fb in demo.get('feedback', {}).values() if fb.get('is_correct') is False
    )
    unanswered_count = question_count - answered_count

    return render(request, 'core/demo/take.html', {
        'demo': demo,
        'question': current_question,
        'options': options,
        'question_number': display_index + 1,
        'question_count': question_count,
        'progress_pct': int(((display_index + 1) / question_count) * 100),
        'answered_count': answered_count,
        'showing_feedback': showing_feedback,
        'feedback': feedback,
        'feedback_index': feedback_index,
        'is_last_question': display_index + 1 == question_count,
        'nav_states': nav_states,
        'correct_count': correct_count,
        'incorrect_count': incorrect_count,
        'unanswered_count': unanswered_count,
        'question_uuid': qid,
    })


@require_GET
def demo_results_view(request):
    demo = get_demo_session(request)
    if not demo:
        return redirect('core:demo_wizard')

    questions = load_demo_questions(demo)
    if not demo.get('completed'):
        finalize_demo(demo, questions)
        save_demo_session(request, demo)

    breakdown = build_demo_breakdown(demo, questions)
    return render(request, 'core/demo/results.html', {
        'demo': demo,
        'breakdown': breakdown,
        'question_count': len(questions),
        'incorrect_count': len(questions) - demo.get('correct_count', 0),
    })


@require_POST
@rate_limit(
    key='demo_ai_explain_burst',
    limit=8,
    window=60,
    by='ip',
    methods=['POST'],
    json_error='Too many AI requests. Please wait a minute and try again.',
)
@rate_limit(
    key='demo_ai_explain_hour',
    limit=40,
    window=3600,
    by='ip',
    methods=['POST'],
    json_error='AI explain limit reached. Please try again later.',
)
def demo_explain_view(request):
    from core.ai import EXPLAIN_ANSWER_TASK, ai_service
    from core.ai.exceptions import AIServiceError
    from core.models import Question

    demo = get_demo_session(request)
    if not demo:
        return JsonResponse({'error': 'No active demo session.'}, status=400)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

    question_uuid = str(payload.get('question_uuid', '')).strip()
    if not question_uuid or question_uuid not in demo.get('question_ids', []):
        return JsonResponse({'error': 'Invalid question for this demo.'}, status=400)

    feedback = demo.get('feedback', {}).get(question_uuid)
    if not feedback or feedback.get('is_correct'):
        return JsonResponse({'error': 'AI explain is only available for incorrect answers.'}, status=400)

    question = get_object_or_404(
        Question.objects.prefetch_related('options'),
        uuid=question_uuid,
        is_active=True,
    )
    choices = [
        {'text': opt.option, 'is_correct': opt.is_correct}
        for opt in question.options.filter(is_active=True).order_by('created_at')
    ]
    if not choices:
        return JsonResponse({'error': 'This question has no choices to explain.'}, status=400)

    try:
        result = ai_service.run(
            EXPLAIN_ANSWER_TASK,
            question=question.quiz,
            choices=choices,
            selected_choice=feedback.get('selected_text', ''),
            grade_level=demo.get('grade_name', ''),
            subject=demo.get('subject_name', ''),
        )
    except AIServiceError as exc:
        return JsonResponse({'error': str(exc)}, status=503)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    return JsonResponse(result)
