"""Parse and grade Matching quiz items."""

import re

PAIR_SEPARATORS = ('→', '->', '=>', ' :: ', ' | ', ' — ', ' – ', ' - ')

_LEFT_LINE_RE = re.compile(
    r'^(?:\d+[\.)]|[A-Za-z][\.\)])\s+(.+)$',
)


def split_matching_pair(text):
    """Split 'Left → Right' style option text. Returns (left, right) or ('', full text)."""
    raw = (text or '').strip()
    if not raw:
        return '', ''
    for sep in PAIR_SEPARATORS:
        if sep in raw:
            left, right = raw.split(sep, 1)
            return left.strip(), right.strip()
    return '', raw


def _parse_left_column_from_quiz(quiz_text):
    """Numbered / lettered lines in the stem often list column A."""
    lines = []
    for line in (quiz_text or '').splitlines():
        line = line.strip()
        if not line:
            continue
        match = _LEFT_LINE_RE.match(line)
        if match:
            lines.append(match.group(1).strip())
    return lines


def pairs_from_metadata(metadata):
    pairs = []
    if not isinstance(metadata, list):
        return pairs
    for item in metadata:
        if isinstance(item, dict):
            left = (
                item.get('left')
                or item.get('a')
                or item.get('prompt')
                or item.get('term')
                or ''
            )
            right = (
                item.get('right')
                or item.get('b')
                or item.get('match')
                or item.get('answer')
                or ''
            )
            left = str(left).strip()
            right = str(right).strip()
            if left and right:
                pairs.append({'left': left, 'right': right})
        elif isinstance(item, str) and item.strip():
            left, right = split_matching_pair(item)
            if left and right:
                pairs.append({'left': left, 'right': right})
    return pairs


def parse_matching_pairs(question):
    """
    Build {left, right} rows for UI and grading.
    Uses metadata, option pairs (→), or stem lines + option texts.
    """
    pairs = pairs_from_metadata(question.metadata)
    if pairs:
        return pairs

    options = list(question.options.filter(is_active=True).order_by('created_at'))
    for opt in options:
        left, right = split_matching_pair(opt.option or '')
        if left and right:
            pairs.append({'left': left, 'right': right})
        elif right:
            pairs.append({'left': '', 'right': right})

    if pairs and all(not p.get('left') for p in pairs):
        left_labels = _parse_left_column_from_quiz(question.quiz)
        for index, pair in enumerate(pairs):
            if index < len(left_labels):
                pair['left'] = left_labels[index]

    pairs = [p for p in pairs if p.get('left') and p.get('right')]
    return pairs


def matching_choice_pool(question):
    """Unique right-column labels for dropdowns."""
    labels = []
    seen = set()
    for pair in parse_matching_pairs(question):
        label = pair['right']
        key = label.casefold()
        if key not in seen:
            seen.add(key)
            labels.append(label)
    if labels:
        return labels
    for opt in question.options.filter(is_active=True).order_by('created_at'):
        text = (opt.option or '').strip()
        if not text:
            continue
        key = text.casefold()
        if key not in seen:
            seen.add(key)
            labels.append(text)
    return labels


def matching_rows_for_display(question):
    """Rows for the take-exam matching UI."""
    pairs = parse_matching_pairs(question)
    if pairs:
        return pairs
    labels = matching_choice_pool(question)
    if not labels:
        return []
    left_labels = _parse_left_column_from_quiz(question.quiz)
    if len(left_labels) >= len(labels):
        return [
            {'left': left_labels[i], 'right': ''}
            for i in range(len(labels))
        ]
    return [
        {'left': f'Item {i + 1}', 'right': ''}
        for i in range(len(labels))
    ]


def compose_matching_answer(post_data):
    """Build stored text_answer from POST fields matching_N + matching_left_N."""
    parts = []
    index = 0
    while True:
        left_key = f'matching_left_{index}'
        match_key = f'matching_{index}'
        if left_key not in post_data and match_key not in post_data:
            if index > 0:
                break
            if index == 0 and match_key not in post_data:
                break
        left = (post_data.get(left_key) or '').strip()
        right = (post_data.get(match_key) or '').strip()
        if left and right:
            parts.append(f'{left}={right}')
        index += 1
        if index > 30:
            break
    return '|'.join(parts)


def build_matching_review_rows(question, text_answer=''):
    """Per-row review data for attempt detail (learner vs correct match)."""
    from core.scoring import _normalize_answer_text

    pairs = parse_matching_pairs(question)
    if not pairs:
        return []
    learner_map = parse_matching_submission(text_answer)
    if not learner_map:
        return []
    rows = []
    for pair in pairs:
        left = pair['left']
        expected = pair['right']
        given = (learner_map.get(left) or '').strip()
        rows.append({
            'left': left,
            'expected': expected,
            'given': given if given else '—',
            'is_correct': bool(given)
            and _normalize_answer_text(given) == _normalize_answer_text(expected),
            'answered': bool(given),
        })
    return rows


def format_matching_submission_summary(text_answer):
    """Human-readable summary of a stored matching answer."""
    learner_map = parse_matching_submission(text_answer)
    if not learner_map:
        return ''
    return '; '.join(f'{left} → {right}' for left, right in sorted(learner_map.items()))


def parse_matching_submission(answer_str):
    """Parse stored answer into {left: right}."""
    result = {}
    if not answer_str:
        return result
    text = str(answer_str).strip()
    if not text:
        return result
    for chunk in text.split('|'):
        chunk = chunk.strip()
        if not chunk or '=' not in chunk:
            continue
        left, right = chunk.split('=', 1)
        left = left.strip()
        right = right.strip()
        if left and right:
            result[left] = right
    return result
