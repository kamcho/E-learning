from ..client import OpenAIClient

EXPLAIN_ANSWER_TASK = 'explain_answer'

SYSTEM_PROMPT = """You are a friendly CBC (Competency-Based Curriculum) tutor for Kenyan learners.
Explain quiz answers clearly and briefly using simple language suited to the learner's level.
Focus on why the correct answer is right. If the learner picked a wrong answer, gently explain
their mistake without being discouraging. Keep responses under 150 words."""


class ExplainAnswerTask:
    """Explain why the correct answer to a question is correct."""

    task_name = EXPLAIN_ANSWER_TASK

    def __init__(self, client=None):
        self.client = client or OpenAIClient()

    def run(
        self,
        *,
        question: str,
        choices: list[dict],
        selected_choice: str,
        grade_level: str = '',
        subject: str = '',
    ) -> dict:
        """
        Generate an explanation for a multiple-choice style question.

        choices: [{"text": str, "is_correct": bool}, ...]
        selected_choice: the option text the learner chose
        """
        if not question or not question.strip():
            raise ValueError('Question text is required.')
        if not choices:
            raise ValueError('At least one choice is required.')

        correct_choices = [c['text'] for c in choices if c.get('is_correct')]
        if not correct_choices:
            raise ValueError('No correct choice was provided.')

        user_prompt = self._build_prompt(
            question=question.strip(),
            choices=choices,
            selected_choice=(selected_choice or '').strip(),
            correct_choices=correct_choices,
            grade_level=grade_level,
            subject=subject,
        )
        explanation = self.client.chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return {
            'task': self.task_name,
            'explanation': explanation,
            'correct_answer': correct_choices[0],
            'learner_was_correct': (selected_choice or '').strip() in correct_choices,
        }

    def _build_prompt(
        self,
        *,
        question: str,
        choices: list[dict],
        selected_choice: str,
        correct_choices: list[str],
        grade_level: str,
        subject: str,
    ) -> str:
        choice_lines = []
        for index, choice in enumerate(choices):
            letter = chr(65 + index)
            marker = ' (correct)' if choice.get('is_correct') else ''
            choice_lines.append(f"{letter}. {choice['text']}{marker}")

        context_parts = []
        if grade_level:
            context_parts.append(f"Grade level: {grade_level}")
        if subject:
            context_parts.append(f"Subject: {subject}")
        context_block = '\n'.join(context_parts)

        learner_line = selected_choice or 'No answer selected'
        correct_line = '; '.join(correct_choices)

        return f"""Explain this exam question to the learner.

{f"Context:{chr(10)}{context_block}{chr(10)}" if context_block else ""}
Question:
{question}

Choices:
{chr(10).join(choice_lines)}

Learner's selected answer: {learner_line}
Correct answer(s): {correct_line}

Explain why the correct answer is right. If the learner was wrong, briefly say why their choice
does not work and guide them toward the correct reasoning."""
