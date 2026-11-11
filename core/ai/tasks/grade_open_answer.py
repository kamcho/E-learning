import json

from ..client import OpenAIClient
from ..exceptions import AITaskError

GRADE_OPEN_ANSWER_TASK = 'grade_open_answer'

SYSTEM_PROMPT = """You are a fair CBE (Competency-Based Education) examiner for Kenyan schools.
Grade short learner answers against the question and any reference answers provided.

Rules:
- Accept answers that are substantially correct, even with minor spelling or wording differences.
- For numerics, accept equivalent forms (e.g. 3/4, 0.75, and $\\frac{3}{4}$) when clearly the same value.
- When the question asks for a final amount, total, or result, mark correct if that final value is right,
  even if the learner did not show every step of working. Phrases like "show your working" are guidance,
  not a reason to fail a correct final answer alone (e.g. "3/4" for 1/2 + 1/4 flour).
- If reference answers are listed, accept any answer that matches their meaning or numeric value.
- Reject empty, unrelated, or clearly wrong answers.
- Be encouraging but accurate for primary and junior secondary learners.

Respond with JSON only, no markdown:
{"is_correct": true or false, "reason": "one brief sentence for teachers/guardians"}"""


class GradeOpenAnswerTask:
    """AI marker for open-ended and similar free-text responses."""

    task_name = GRADE_OPEN_ANSWER_TASK

    def __init__(self, client=None):
        self.client = client or OpenAIClient()

    def run(
        self,
        *,
        question: str,
        learner_answer: str,
        reference_answers: list[str] | None = None,
        max_marks: int = 1,
        grade_level: str = '',
        subject: str = '',
    ) -> dict:
        question = (question or '').strip()
        learner_answer = (learner_answer or '').strip()
        if not question:
            raise ValueError('Question text is required.')
        if not learner_answer:
            return {
                'task': self.task_name,
                'is_correct': False,
                'reason': 'No answer was provided.',
            }

        reference_answers = [a.strip() for a in (reference_answers or []) if a and str(a).strip()]
        context_lines = []
        if grade_level:
            context_lines.append(f'Grade level: {grade_level}')
        if subject:
            context_lines.append(f'Subject: {subject}')
        context_lines.append(f'Max marks: {max_marks}')

        ref_block = ''
        if reference_answers:
            ref_block = 'Reference answer(s) (acceptable):\n' + '\n'.join(
                f'- {text}' for text in reference_answers
            )
        else:
            ref_block = 'No reference answer was supplied — use the question and CBE expectations.'

        user_prompt = f"""{'\n'.join(context_lines)}

Question:
{question}

{ref_block}

Learner's answer:
{learner_answer}

Return is_correct true only if the learner deserves full credit ({max_marks} mark(s))."""

        raw = self.client.chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
            json_mode=True,
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AITaskError('AI grading returned invalid JSON.') from exc

        if 'is_correct' not in data:
            raise AITaskError('AI grading response missing is_correct.')

        return {
            'task': self.task_name,
            'is_correct': bool(data['is_correct']),
            'reason': str(data.get('reason', '')).strip(),
        }
