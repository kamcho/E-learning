"""Normalize plain math text for MathJax display (import + review)."""

import re

_PLAIN_FRACTION = re.compile(
    r'(?<!\$)(?<![\w\\])(\d{1,3})\s*/\s*(\d{1,3})(?!\s*/)(?![\d%])',
)
_MIXED_NUMBER = re.compile(
    r'(?<!\$)(?<![\w\\])(\d+)\s+(\d{1,2})\s*/\s*(\d{1,2})(?!\s*/)(?![\d%])',
)
# AI JSON often emits "\frac" which JSON parses as form-feed (\\f) + "rac".
_FORM_FEED_FRAC = re.compile(r'\x0c\s*rac(\{|\b)')
_DIGIT_BROKEN_FRAC = re.compile(r'(\d)\s*rac\{')
_BARE_RAC = re.compile(r'(?<!\\)(?<![A-Za-z$])rac\{')
_TAB_TIMES = re.compile(r'\t+\s*imes\b')


def repair_broken_latex_escapes(text: str) -> str:
    """Fix LaTeX corrupted by JSON \\f, \\t, or missing backslashes after AI/import."""
    if not text:
        return text
    text = _FORM_FEED_FRAC.sub(r'\\frac\1', text)
    text = _DIGIT_BROKEN_FRAC.sub(r'\1\\frac{', text)
    text = _BARE_RAC.sub(r'\\frac{', text)
    text = _TAB_TIMES.sub(r'\\times', text)
    text = text.replace('\x0c', '')
    text = text.replace('\x08eta', '\\beta')
    text = text.replace('\x08ar', '\\bar')
    return text


def finalize_math_display_text(text: str) -> str:
    """Repair JSON/AI glitches, then normalize plain fractions for MathJax."""
    text = repair_broken_latex_escapes((text or '').strip())
    return normalize_question_math_text(text)


def normalize_question_math_text(text: str) -> str:
    """
    Light cleanup for AI/imported stems and options: blanks, mixed numbers, simple a/b fractions.
    Does not change wording; safe to run before save and on preview.
    """
    if not text:
        return text
    text = repair_broken_latex_escapes(text.strip())
    blank = r'$\underline{\quad\quad\quad}$'
    text = text.replace(r'\_\_\_', blank)
    text = re.sub(r'\\{3,}', lambda _m: blank, text)

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
            lambda _m, cmd=command: f'$\\{cmd}$',
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
