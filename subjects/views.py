from functools import wraps

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django import forms
from django.db import IntegrityError
from django.db.models import Count

from core.ai.exceptions import AIServiceError
from core.forms import QuestionCreateForm
from core.models import Option, Question

from .curriculum_import import (
    CurriculumImportError,
    create_curriculum,
    load_curriculum_preview,
    parse_curriculum_text,
    sign_curriculum_preview,
)
from .models import (
    GradeLevel, Discipline, Subject, Strand, 
    SubStrand, StrandObjective, SubStrandObjective
)
from .forms import (
    GradeLevelForm, DisciplineForm, SubjectForm, 
    StrandForm, SubStrandForm, StrandObjectiveForm, 
    SubStrandObjectiveForm
)


def admin_curriculum_required(view_func):
    """Restrict curriculum configuration views to platform admins."""
    @login_required(login_url='accounts:signin')
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not (user.is_admin_role or user.is_staff):
            messages.error(request, "You don't have permission to access curriculum configuration.")
            if user.is_guardian:
                return redirect('accounts:guardian_dashboard')
            return redirect('core:landing')
        return view_func(request, *args, **kwargs)
    return wrapper


# ═══════════════ GRADE LEVEL VIEWS ═══════════════

@admin_curriculum_required
def grade_level_list(request):
    """List all Grade Levels and handle creation of a new Grade Level."""
    from .grade_analytics import build_grade_level_cards

    grade_levels = GradeLevel.objects.all()
    if request.method == 'POST':
        form = GradeLevelForm(request.POST)
        if form.is_valid():
            grade_level = form.save()
            messages.success(request, f"Grade Level '{grade_level.name}' created successfully!")
            return redirect('subjects:grade_level_list')
        else:
            messages.error(request, "Failed to create Grade Level. Please correct the errors below.")
    else:
        form = GradeLevelForm()

    return render(request, 'subjects/grade_level_list.html', {
        'grade_levels': grade_levels,
        'grade_cards': build_grade_level_cards(grade_levels),
        'form': form,
    })


@admin_curriculum_required
def grade_level_detail(request, slug):
    """View details of a Grade Level and handle creation of a child Subject."""
    from .grade_analytics import build_grade_detail_summary, build_subject_analytics_rows

    grade_level = get_object_or_404(GradeLevel, slug=slug)

    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save(commit=False)
            subject.grade_level = grade_level
            subject.save()
            messages.success(request, f"Subject '{subject.name}' added to {grade_level.name}!")
            return redirect('subjects:grade_level_detail', slug=grade_level.slug)
        else:
            messages.error(request, "Failed to add Subject. Please check the form errors.")
    else:
        form = SubjectForm(initial={'grade_level': grade_level})
        form.fields['grade_level'].widget = forms.HiddenInput()

    return render(request, 'subjects/grade_level_detail.html', {
        'grade_level': grade_level,
        'summary': build_grade_detail_summary(grade_level),
        'subject_rows': build_subject_analytics_rows(grade_level),
        'form': form,
    })


# ═══════════════ DISCIPLINE VIEWS ═══════════════

@admin_curriculum_required
def discipline_list(request):
    """List all Disciplines and handle creation of a new Discipline."""
    disciplines = Discipline.objects.all()
    if request.method == 'POST':
        form = DisciplineForm(request.POST)
        if form.is_valid():
            discipline = form.save()
            messages.success(request, f"Discipline '{discipline.name}' created successfully!")
            return redirect('subjects:discipline_list')
        else:
            messages.error(request, "Failed to create Discipline. Please correct the errors below.")
    else:
        form = DisciplineForm()
        
    return render(request, 'subjects/discipline_list.html', {
        'disciplines': disciplines,
        'form': form
    })

@admin_curriculum_required
def discipline_detail(request, slug):
    """View details of a Discipline and handle creation of a child Subject."""
    discipline = get_object_or_404(Discipline, slug=slug)
    subjects = discipline.subjects.all()
    
    if request.method == 'POST':
        # Create a Subject under this Discipline
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save(commit=False)
            subject.discipline = discipline
            subject.save()
            messages.success(request, f"Subject '{subject.name}' added to {discipline.name}!")
            return redirect('subjects:discipline_detail', slug=discipline.slug)
        else:
            messages.error(request, "Failed to add Subject. Please check the form errors.")
    else:
        form = SubjectForm(initial={'discipline': discipline})
        form.fields['discipline'].widget = forms.HiddenInput()

    return render(request, 'subjects/discipline_detail.html', {
        'discipline': discipline,
        'subjects': subjects,
        'form': form
    })


# ═══════════════ SUBJECT VIEWS ═══════════════

DEFAULT_SUBJECT_LIST_GRADE_SLUG = 'grade-6'


def _subject_list_redirect(request):
    """Preserve grade filter when redirecting after POST."""
    grade_param = request.GET.get('grade')
    if grade_param:
        return redirect(f"{reverse('subjects:subject_list')}?grade={grade_param}")
    return redirect('subjects:subject_list')


@admin_curriculum_required
def subject_list(request):
    """List subjects with grade-level filtering (defaults to Grade 6)."""
    grade_param = request.GET.get('grade')
    show_all_grades = grade_param == 'all'
    if show_all_grades:
        grade_slug = ''
    elif grade_param is None:
        grade_slug = DEFAULT_SUBJECT_LIST_GRADE_SLUG
    else:
        grade_slug = grade_param.strip()

    all_grade_levels = GradeLevel.objects.all().order_by('name')
    subjects = Subject.objects.all().select_related('grade_level', 'discipline')

    active_grade = None
    if not show_all_grades and grade_slug:
        active_grade = GradeLevel.objects.filter(slug=grade_slug).first()
        if active_grade:
            subjects = subjects.filter(grade_level=active_grade)
        elif grade_param is None:
            active_grade = GradeLevel.objects.filter(
                slug=DEFAULT_SUBJECT_LIST_GRADE_SLUG,
            ).first()
            if active_grade:
                subjects = subjects.filter(grade_level=active_grade)

    subjects = subjects.order_by('grade_level__name', 'name')

    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save()
            messages.success(request, f"Subject '{subject.name}' created successfully!")
            return _subject_list_redirect(request)
        messages.error(request, "Failed to create Subject. Please correct the errors below.")
    else:
        initial = {}
        if active_grade:
            initial['grade_level'] = active_grade
        form = SubjectForm(initial=initial)

    return render(request, 'subjects/subject_list.html', {
        'subjects': subjects,
        'form': form,
        'all_grade_levels': all_grade_levels,
        'active_grade': active_grade,
        'show_all_grades': show_all_grades,
    })

@admin_curriculum_required
def subject_detail(request, slug):
    """Subject detail: all strands for this subject + add strand form."""
    subject = get_object_or_404(
        Subject.objects.select_related('grade_level', 'discipline'),
        slug=slug,
    )
    strands = (
        subject.strands
        .annotate(sub_strand_count=Count('sub_strands'))
        .order_by('order', 'name')
    )

    action = request.POST.get('action', 'create_strand') if request.method == 'POST' else None
    curriculum_text = ''
    curriculum_preview = None
    curriculum_preview_token = ''

    if request.method == 'POST' and action == 'parse_curriculum':
        curriculum_text = request.POST.get('curriculum_text', '')
        form = StrandForm(initial={'subject': subject})
        try:
            curriculum_preview = parse_curriculum_text(curriculum_text, subject)
            curriculum_preview_token = sign_curriculum_preview(curriculum_preview)
        except (AIServiceError, CurriculumImportError) as exc:
            messages.error(request, str(exc))
    elif request.method == 'POST' and action == 'import_curriculum':
        form = StrandForm(initial={'subject': subject})
        try:
            curriculum = load_curriculum_preview(request.POST.get('preview_token', ''))
            created_strands, created_sub_strands = create_curriculum(subject, curriculum)
        except (AIServiceError, CurriculumImportError, IntegrityError) as exc:
            messages.error(request, f'Curriculum import failed: {exc}')
        else:
            messages.success(
                request,
                f'Curriculum imported: {created_strands} strand(s) and '
                f'{created_sub_strands} sub-strand(s) created. Existing entries were kept.',
            )
            return redirect('subjects:subject_detail', slug=subject.slug)
    elif request.method == 'POST':
        form = StrandForm(request.POST)
        if form.is_valid():
            strand = form.save(commit=False)
            strand.subject = subject
            strand.save()
            messages.success(request, f"Strand '{strand.name}' created under {subject.name}!")
            return redirect('subjects:subject_detail', slug=subject.slug)
        messages.error(request, "Failed to create Strand. Please check the form errors.")
    else:
        form = StrandForm(initial={'subject': subject})

    form.fields['subject'].widget = forms.HiddenInput()

    return render(request, 'subjects/subject_detail.html', {
        'subject': subject,
        'strands': strands,
        'strand_count': strands.count(),
        'form': form,
        'curriculum_text': curriculum_text,
        'curriculum_preview': curriculum_preview,
        'curriculum_preview_token': curriculum_preview_token,
    })


# ═══════════════ STRAND VIEWS ═══════════════

def strand_detail(request, slug):
    """Strand detail: all sub-strands under this strand + add sub-strand form."""
    strand = get_object_or_404(
        Strand.objects.select_related('subject', 'subject__grade_level', 'subject__discipline'),
        slug=slug,
    )
    sub_strands = strand.sub_strands.all().order_by('order', 'name')
    objectives = strand.strand_objectives.all().order_by('order', 'name')

    action = request.POST.get('action') if request.method == 'POST' else None

    if request.method == 'POST' and action == 'create_substrand':
        substrand_form = SubStrandForm(request.POST, prefix='substrand')
        objective_form = StrandObjectiveForm(prefix='objective', initial={'strand': strand})
        if substrand_form.is_valid():
            sub_strand = substrand_form.save(commit=False)
            sub_strand.strand = strand
            sub_strand.save()
            messages.success(request, f"Sub-strand '{sub_strand.name}' created!")
            return redirect('subjects:strand_detail', slug=strand.slug)
        messages.error(request, "Failed to create Sub-strand.")
    elif request.method == 'POST' and action == 'create_objective':
        substrand_form = SubStrandForm(prefix='substrand', initial={'strand': strand})
        objective_form = StrandObjectiveForm(request.POST, prefix='objective')
        if objective_form.is_valid():
            objective = objective_form.save(commit=False)
            objective.strand = strand
            objective.save()
            messages.success(request, f"Objective '{objective.name}' added to Strand!")
            return redirect('subjects:strand_detail', slug=strand.slug)
        messages.error(request, "Failed to add Objective.")
    else:
        substrand_form = SubStrandForm(prefix='substrand', initial={'strand': strand})
        objective_form = StrandObjectiveForm(prefix='objective', initial={'strand': strand})

    substrand_form.fields['strand'].widget = forms.HiddenInput()
    objective_form.fields['strand'].widget = forms.HiddenInput()

    return render(request, 'subjects/strand_detail.html', {
        'strand': strand,
        'sub_strands': sub_strands,
        'sub_strand_count': sub_strands.count(),
        'objectives': objectives,
        'substrand_form': substrand_form,
        'objective_form': objective_form,
    })


# ═══════════════ SUB-STRAND VIEWS ═══════════════

def sub_strand_detail(request, slug):
    """Sub-strand detail: objectives under this sub-strand."""
    sub_strand = get_object_or_404(
        SubStrand.objects.select_related(
            'strand', 'strand__subject', 'strand__subject__grade_level',
        ),
        slug=slug,
    )
    objectives = sub_strand.sub_strand_objectives.all().order_by('order', 'name')
    questions = list(
        sub_strand.questions
        .prefetch_related('options')
        .order_by('-created_at')
    )

    if request.method == 'POST':
        form = SubStrandObjectiveForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.sub_strand = sub_strand
            obj.save()
            messages.success(request, f"Sub-strand Objective '{obj.name}' added!")
            return redirect('subjects:sub_strand_detail', slug=sub_strand.slug)
        else:
            messages.error(request, "Failed to add Objective.")
    else:
        form = SubStrandObjectiveForm(initial={'sub_strand': sub_strand})
        form.fields['sub_strand'].widget = forms.HiddenInput()

    return render(request, 'subjects/sub_strand_detail.html', {
        'sub_strand': sub_strand,
        'objectives': objectives,
        'questions': questions,
        'question_count': len(questions),
        'form': form,
    })


# ═══════════════ QUESTION CREATION (SUBJECT-LEVEL) ═══════════════

def _resolve_question_sub_strand(request, subject):
    """Return a sub-strand scoped to this subject from GET or POST params."""
    raw = request.POST.get('sub_strand_id') if request.method == 'POST' else request.GET.get('sub_strand')
    if not raw:
        return None
    try:
        sub_strand_pk = int(raw)
    except (TypeError, ValueError):
        return None
    return SubStrand.objects.filter(pk=sub_strand_pk, strand__subject_id=subject.pk).first()


@login_required(login_url='accounts:signin')
def create_question_for_subject(request, subject_id):
    """
    Create a Question associated with any SubStrand under the given Subject.

    URL param: `subject_id`.
    """
    user = request.user
    if not (user.is_admin_role or user.is_staff or user.is_teacher):
        messages.error(request, "You don't have permission to create questions.")
        return redirect('core:landing')

    subject = get_object_or_404(Subject, pk=subject_id)
    return_sub_strand = _resolve_question_sub_strand(request, subject)

    if request.method == 'POST':
        form = QuestionCreateForm(
            request.POST,
            request.FILES,
            subject_id=subject.pk,
            sub_strand_id=return_sub_strand.pk if return_sub_strand else None,
        )
        if form.is_valid():
            quiz = form.cleaned_data['quiz'].strip()
            difficulty = form.cleaned_data['difficulty']
            quiz_type = form.cleaned_data['quiz_type']
            sub_strand = form.cleaned_data['sub_strand']

            try:
                question = Question.objects.create(
                    quiz=quiz,
                    difficulty=difficulty,
                    quiz_type=quiz_type,
                    sub_strand=sub_strand,
                    score=0,
                    metadata=[],
                    is_active=True,
                    created_by=user,
                    prompt_image=form.cleaned_data.get('prompt_image'),
                    prompt_audio=form.cleaned_data.get('prompt_audio'),
                    image_alt_text=(form.cleaned_data.get('image_alt_text') or '').strip(),
                )
            except Exception as e:
                messages.error(request, f"Failed to create question: {e}")
                return render(request, 'subjects/create_question.html', {
                    'subject': subject,
                    'form': form,
                    'return_sub_strand': return_sub_strand,
                })

            # Create Options when required by quiz_type
            if quiz_type == "Multiple Choice":
                for idx in range(1, 5):
                    txt = (form.cleaned_data.get(f"option_{idx}") or "").strip()
                    option_image = form.cleaned_data.get(f"option_{idx}_image")
                    if not txt and not option_image:
                        continue
                    Option.objects.create(
                        question=question,
                        option=txt,
                        option_image=option_image,
                        is_correct=form.cleaned_data.get(f"correct_{idx}") is True,
                        is_active=True,
                    )

            elif quiz_type == "True or False":
                true_txt = (form.cleaned_data.get("option_1") or "True").strip() or "True"
                false_txt = (form.cleaned_data.get("option_2") or "False").strip() or "False"
                try:
                    Option.objects.create(
                        question=question,
                        option=true_txt,
                        is_correct=form.cleaned_data.get("correct_1") is True,
                        is_active=True,
                    )
                    Option.objects.create(
                        question=question,
                        option=false_txt,
                        is_correct=form.cleaned_data.get("correct_2") is True,
                        is_active=True,
                    )
                except Exception as e:
                    messages.error(request, f"Question created, but failed to create options: {e}")
                    if return_sub_strand:
                        return redirect('subjects:sub_strand_detail', slug=return_sub_strand.slug)
                    return redirect('subjects:subject_detail', slug=subject.slug)

            messages.success(request, "Question created successfully!")
            if return_sub_strand:
                return redirect('subjects:sub_strand_detail', slug=return_sub_strand.slug)
            return redirect('subjects:subject_detail', slug=subject.slug)
    else:
        form = QuestionCreateForm(
            subject_id=subject.pk,
            sub_strand_id=return_sub_strand.pk if return_sub_strand else None,
        )

    return render(request, 'subjects/create_question.html', {
        'subject': subject,
        'form': form,
        'return_sub_strand': return_sub_strand,
    })
