"""Normalize plain math text for MathJax display (import + review)."""

import re

_PLAIN_FRACTION = re.compile(
    r'(?<!\$)(?<![\w\\])(\d{1,3})\s*/\s*(\d{1,3})(?!\s*/)(?![\d%])',
)
_MIXED_NUMBER = re.compile(
    r'(?<!\$)(?<![\w\\])(\d+)\s+(\d{1,2})\s*/\s*(\d{1,2})(?!\s*/)(?![\d%])',
)


def normalize_question_math_text(text: str) -> str:
    """
    Light cleanup for AI/imported stems and options: blanks, mixed numbers, simple a/b fractions.
    Does not change wording; safe to run before save and on preview.
    """
    if not text:
        return text
    text = text.strip()
    blank = r'$\underline{\quad\quad\quad}$'
    text = text.replace(r'\_\_\_', blank)
    text = re.sub(r'\\{3,}', blank, text)

    def mixed_replace(match):
        whole, num, den = match.group(1), match.group(2), match.group(3)
        return f'${whole}\\frac{{{num}}}{{{den}}}$'

    text = _MIXED_NUMBER.sub(mixed_replace, text)

    def frac_replace(match):
        num, den = match.group(1), match.group(2)
        return f'$\\frac{{{num}}}{{{den}}}$'

    text = _PLAIN_FRACTION.sub(frac_replace, text)

    # Common LaTeX commands pasted without $ delimiters (one command at a time).
    for command in ('leq', 'geq', 'times', 'div', 'cdot', 'pm'):
        text = re.sub(
            rf'(?<!\$)\\{command}(?!\w)',
            rf'$\\{command}$',
            text,
        )

    # Collapse accidental adjacent dollar pairs from repeated passes.
    text = text.replace('$$', '$')
    return text


def normalize_question_item_math(data: dict) -> dict:
    """Return a copy of a question dict with normalized quiz + choice text."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    if out.get('quiz'):
        out['quiz'] = normalize_question_math_text(str(out['quiz']))
    choices = out.get('choices')
    if isinstance(choices, list):
        new_choices = []
        for choice in choices:
            if not isinstance(choice, dict):
                new_choices.append(choice)
                continue
            row = dict(choice)
            if row.get('option'):
                row['option'] = normalize_question_math_text(str(row['option']))
            new_choices.append(row)
        out['choices'] = new_choices
    return out
