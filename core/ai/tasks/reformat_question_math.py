import json

from ..client import OpenAIClient
from ..exceptions import AITaskError

REFORMAT_QUESTION_MATH_TASK = 'reformat_question_math'

SYSTEM_PROMPT = """You are a Kenya CBC mathematics editor for the Soma Smart e-learning platform.
Reformat assessment question text so fractions and number sequences display with MathJax/LaTeX.

Rules:
- Keep the same meaning, wording, difficulty, and which answers are correct. Do NOT change pedagogy.
- Use $...$ for inline math only (not \\(...\\)).
- Fractions: $\\frac{1}{3}$, mixed numbers: $1\\frac{1}{4}$, multiplication: $\\times$ or $\\cdot$ when needed.
- Sequences like 1/3, 1/2, 2/3, 5/6 may stay as comma-separated $\\frac{1}{3}$, $\\frac{1}{2}$, $\\frac{2}{3}$, $\\frac{5}{6}$ inside one $...$ group or as separate $...$ tokens — pick the clearer layout.
- Replace broken blank markers (e.g. \\_\\_\\_ , ___) with $\\underline{\\quad\\quad\\quad}$ or plain "______" outside math if it reads better.
- Fix stray backslashes from bad imports (e.g. \\_\\_\\_) without doubling backslashes for the database (single backslashes in JSON strings for LaTeX commands like \\frac).
- Plain English words stay outside $...$.
- For True/False or text-only options with no numbers, return unchanged unless a fraction is present.

Return JSON only (no markdown):
{
  "quiz": "reformatted stem",
  "options": [{"uuid": "<same uuid as input>", "option": "reformatted choice text"}, ...]
}
Every input option uuid must appear exactly once in the same order."""


class ReformatQuestionMathTask:
    """Rewrite question stem and choices with consistent LaTeX for math rendering."""

    task_name = REFORMAT_QUESTION_MATH_TASK

    def __init__(self, client=None):
        self.client = client or OpenAIClient()

    def run(
        self,
        *,
        quiz: str,
        quiz_type: str,
        options: list[dict],
        grade_level: str = '',
        subject: str = '',
    ) -> dict:
        quiz = (quiz or '').strip()
        if not quiz:
            raise ValueError('Question text is required.')

        option_rows = []
        for row in options:
            option_rows.append({
                'uuid': str(row['uuid']),
                'option': (row.get('option') or '').strip(),
                'is_correct': bool(row.get('is_correct')),
            })

        context = []
        if grade_level:
            context.append(f'Grade: {grade_level}')
        if subject:
            context.append(f'Subject: {subject}')
        if quiz_type:
            context.append(f'Question type: {quiz_type}')
        context_block = '\n'.join(context) if context else 'Grade: primary/junior secondary mathematics'

        user_prompt = f"""{context_block}

Question stem:
{quiz}

Options (keep uuid; only reformat option text):
{json.dumps(option_rows, ensure_ascii=False, indent=2)}"""

        client = OpenAIClient(
            model=self.client.model,
            api_key=self.client.api_key,
            timeout=self.client.timeout,
            max_tokens=max(500, self.client.max_tokens),
        )
        raw = client.chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
            json_mode=True,
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AITaskError('AI reformat returned invalid JSON.') from exc

        if not isinstance(data.get('quiz'), str):
            raise AITaskError('AI reformat response missing quiz text.')

        out_options = data.get('options')
        if not isinstance(out_options, list):
            raise AITaskError('AI reformat response missing options array.')

        expected_uuids = [row['uuid'] for row in option_rows]
        by_uuid = {}
        for item in out_options:
            if not isinstance(item, dict):
                continue
            uid = str(item.get('uuid', '')).strip()
            if uid and isinstance(item.get('option'), str):
                by_uuid[uid] = item['option'].strip()

        normalized = []
        for uid in expected_uuids:
            if uid not in by_uuid:
                raise AITaskError(f'AI reformat did not return option uuid {uid}.')
            normalized.append({'uuid': uid, 'option': by_uuid[uid]})

        return {
            'task': self.task_name,
            'quiz': data['quiz'].strip(),
            'options': normalized,
        }
