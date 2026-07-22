"""Validate and bulk-create questions (+ options) from JSON payloads."""

from django.db import IntegrityError, transaction

from core.models import Option, Question
from subjects.models import SubStrand

VALID_DIFFICULTIES = {choice[0] for choice in Question.DIFFICULTY_CHOICES}
VALID_QUIZ_TYPES = {choice[0] for choice in Question.QUIZ_TYPE_CHOICES}


def _resolve_sub_strand(data):
    """Return SubStrand from sub_strand_id or sub_strand_slug."""
    sub_strand_id = data.get('sub_strand_id')
    sub_strand_slug = (data.get('sub_strand_slug') or '').strip()

    if sub_strand_id is not None:
        try:
            pk = int(sub_strand_id)
        except (TypeError, ValueError):
            raise ValueError('sub_strand_id must be an integer.')
        sub_strand = SubStrand.objects.filter(pk=pk).first()
        if not sub_strand:
            raise ValueError(f'Sub-strand with id {pk} was not found.')
        return sub_strand

    if sub_strand_slug:
        sub_strand = SubStrand.objects.filter(slug=sub_strand_slug).first()
        if not sub_strand:
            raise ValueError(f'Sub-strand with slug "{sub_strand_slug}" was not found.')
        return sub_strand

    raise ValueError('Either sub_strand_id or sub_strand_slug is required.')


def _normalize_choices(raw_choices):
    if raw_choices is None:
        return []
    if not isinstance(raw_choices, list):
        raise ValueError('choices must be a list.')
    normalized = []
    for idx, item in enumerate(raw_choices):
        if not isinstance(item, dict):
            raise ValueError(f'choices[{idx}] must be an object.')
        option_text = (item.get('option') or '').strip()
        if not option_text:
            raise ValueError(f'choices[{idx}].option is required.')
        normalized.append({
            'option': option_text,
            'is_correct': bool(item.get('is_correct', False)),
            'is_active': bool(item.get('is_active', True)),
        })
    return normalized


def _validate_choices_for_quiz_type(quiz_type, choices):
    correct_count = sum(1 for choice in choices if choice['is_correct'])

    if quiz_type == 'Multiple Choice':
        if len(choices) < 2:
            raise ValueError('Multiple Choice questions require at least 2 choices.')
        if correct_count < 1:
            raise ValueError('Multiple Choice questions require at least one correct choice.')

    elif quiz_type == 'True or False':
        if len(choices) != 2:
            raise ValueError('True or False questions require exactly 2 choices.')
        if correct_count != 1:
            raise ValueError('True or False questions require exactly one correct choice.')

    elif quiz_type == 'Fill in the Blank':
        if correct_count < 1:
            raise ValueError('Fill in the Blank questions require at least one correct choice.')

    elif quiz_type in ('OpenEnded', 'Matching'):
        return

    else:
        raise ValueError(f'Unsupported quiz_type "{quiz_type}".')


def validate_question_item(data, index=0):
    """Validate one question object; return cleaned dict ready for create."""
    if not isinstance(data, dict):
        raise ValueError(f'questions[{index}] must be an object.')

    quiz = (data.get('quiz') or '').strip()
    if not quiz:
        raise ValueError(f'questions[{index}].quiz is required.')

    difficulty = (data.get('difficulty') or '').strip()
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError(
            f'questions[{index}].difficulty must be one of: {", ".join(sorted(VALID_DIFFICULTIES))}.'
        )

    quiz_type = (data.get('quiz_type') or '').strip()
    if quiz_type not in VALID_QUIZ_TYPES:
        raise ValueError(
            f'questions[{index}].quiz_type must be one of: {", ".join(sorted(VALID_QUIZ_TYPES))}.'
        )

    sub_strand = _resolve_sub_strand(data)
    choices = _normalize_choices(data.get('choices'))
    _validate_choices_for_quiz_type(quiz_type, choices)

    metadata = data.get('metadata', [])
    if metadata is None:
        metadata = []
    if not isinstance(metadata, list):
        raise ValueError(f'questions[{index}].metadata must be a list.')

    score = data.get('score', 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        raise ValueError(f'questions[{index}].score must be an integer.')

    return {
        'quiz': quiz,
        'difficulty': difficulty,
        'quiz_type': quiz_type,
        'sub_strand': sub_strand,
        'choices': choices,
        'metadata': metadata,
        'score': score,
        'image_alt_text': (data.get('image_alt_text') or '').strip(),
    }


def create_question_from_item(cleaned, created_by):
    """Create one inactive question and its options; return uuids."""
    with transaction.atomic():
        question = Question.objects.create(
            quiz=cleaned['quiz'],
            difficulty=cleaned['difficulty'],
            quiz_type=cleaned['quiz_type'],
            sub_strand=cleaned['sub_strand'],
            score=cleaned['score'],
            metadata=cleaned['metadata'],
            image_alt_text=cleaned['image_alt_text'],
            is_active=False,
            created_by=created_by,
        )

        choice_uuids = []
        for choice in cleaned['choices']:
            option = Option.objects.create(
                question=question,
                option=choice['option'],
                is_correct=choice['is_correct'],
                is_active=choice['is_active'],
            )
            choice_uuids.append(str(option.uuid))

    return str(question.uuid), choice_uuids


def bulk_create_questions(payload, created_by):
    """
    Create questions from a payload like {"questions": [...]}.
    Returns summary dict with per-item results.
    """
    if not isinstance(payload, dict):
        raise ValueError('Request body must be a JSON object.')

    raw_questions = payload.get('questions')
    if raw_questions is None:
        raise ValueError('"questions" is required.')
    if not isinstance(raw_questions, list):
        raise ValueError('"questions" must be a list.')
    if not raw_questions:
        raise ValueError('"questions" must not be empty.')

    results = []
    created_count = 0
    failed_count = 0

    for index, item in enumerate(raw_questions):
        try:
            cleaned = validate_question_item(item, index=index)
            question_uuid, choice_uuids = create_question_from_item(cleaned, created_by)
            results.append({
                'index': index,
                'status': 'created',
                'question_uuid': question_uuid,
                'choice_uuids': choice_uuids,
            })
            created_count += 1
        except IntegrityError:
            failed_count += 1
            results.append({
                'index': index,
                'status': 'failed',
                'error': (
                    'A question with the same prompt already exists in this sub-strand, '
                    'or a duplicate choice was provided.'
                ),
            })
        except ValueError as exc:
            failed_count += 1
            results.append({
                'index': index,
                'status': 'failed',
                'error': str(exc),
            })

    return {
        'created': created_count,
        'failed': failed_count,
        'results': results,
    }
