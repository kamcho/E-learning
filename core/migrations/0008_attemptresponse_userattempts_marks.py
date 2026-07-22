import uuid

from django.db import migrations, models
import django.db.models.deletion


def _question_max_marks(question):
    return question.score if question.score > 0 else 1


def migrate_answers_to_responses(apps, schema_editor):
    UserAttempts = apps.get_model('core', 'UserAttempts')
    AttemptResponse = apps.get_model('core', 'AttemptResponse')
    Option = apps.get_model('core', 'Option')

    for attempt in UserAttempts.objects.select_related('quiz').iterator():
        answers = attempt.answers or {}
        if not answers and not attempt.is_complete:
            continue

        questions = attempt.quiz.questions.filter(is_active=True).order_by('created_at')
        marks_earned = 0
        marks_possible = 0

        for question in questions:
            max_marks = _question_max_marks(question)
            marks_possible += max_marks
            selected = str(answers.get(str(question.uuid), '')).strip()
            if not selected:
                continue

            selected_option = None
            text_answer = ''
            marks_awarded = 0
            is_correct = None

            if question.quiz_type in ('Multiple Choice', 'True or False'):
                selected_option = Option.objects.filter(
                    uuid=selected, question=question, is_active=True,
                ).first()
                if selected_option and selected_option.is_correct:
                    marks_awarded = max_marks
                    is_correct = True
                elif selected_option:
                    is_correct = False
            else:
                text_answer = selected

            marks_earned += marks_awarded
            AttemptResponse.objects.update_or_create(
                attempt=attempt,
                question=question,
                defaults={
                    'selected_option': selected_option,
                    'text_answer': text_answer,
                    'max_marks': max_marks,
                    'marks_awarded': marks_awarded,
                    'is_correct': is_correct,
                    'graded_by': 'auto',
                },
            )

        if attempt.is_complete and marks_possible:
            attempt.marks_earned = marks_earned
            attempt.marks_possible = marks_possible
            attempt.score = round((marks_earned / marks_possible) * 100)
            attempt.save(update_fields=['marks_earned', 'marks_possible', 'score'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_userattempts_student_quiz_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='userattempts',
            name='marks_earned',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='userattempts',
            name='marks_possible',
            field=models.IntegerField(default=0),
        ),
        migrations.CreateModel(
            name='AttemptResponse',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('text_answer', models.TextField(blank=True)),
                ('marks_awarded', models.IntegerField(default=0)),
                ('max_marks', models.IntegerField(default=1)),
                ('is_correct', models.BooleanField(blank=True, null=True)),
                ('graded_by', models.CharField(
                    choices=[('auto', 'Auto'), ('teacher', 'Teacher'), ('ai', 'AI')],
                    default='auto',
                    max_length=20,
                )),
                ('answered_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('attempt', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='responses',
                    to='core.userattempts',
                )),
                ('question', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='attempt_responses',
                    to='core.question',
                )),
                ('selected_option', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='attempt_responses',
                    to='core.option',
                )),
            ],
            options={
                'verbose_name': 'Attempt Response',
                'verbose_name_plural': 'Attempt Responses',
                'ordering': ('answered_at',),
                'unique_together': {('attempt', 'question')},
            },
        ),
        migrations.RunPython(migrate_answers_to_responses, migrations.RunPython.noop),
    ]
