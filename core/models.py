from subjects.models import Strand
from subjects.models import Subject
import uuid
from django.db import models
from django.conf import settings
from subjects.models import SubStrand
# Create your models here.
class Question(models.Model):
    DIFFICULTY_CHOICES = (
        ("Easy", "Easy"),
        ("Medium", "Medium"),
        ("Hard", "Hard"),
    )
    QUIZ_TYPE_CHOICES = (
        ("Multiple Choice", "Multiple Choice"),
        ("Fill in the Blank", "Fill in the Blank"),
        ("True or False", "True or False"),
        ("OpenEnded", "OpenEnded"),
        ("Matching", "Matching"),
    )
    uuid=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    quiz=models.TextField(blank=True,null=True)
    prompt_image=models.ImageField(
        upload_to='questions/images/%Y/%m/',
        blank=True,
        null=True,
        help_text='Optional illustration or diagram for the question.',
    )
    prompt_audio=models.FileField(
        upload_to='questions/audio/%Y/%m/',
        blank=True,
        null=True,
        help_text='Optional audio narration (MP3, WAV, OGG).',
    )
    image_alt_text=models.CharField(
        max_length=255,
        blank=True,
        help_text='Describe the image for screen readers and learners.',
    )
    score=models.IntegerField(default=0)
    metadata=models.JSONField(default=list,blank=True,null=True)
    difficulty=models.CharField(max_length=50, choices=DIFFICULTY_CHOICES)
    quiz_type=models.CharField(max_length=50, choices=QUIZ_TYPE_CHOICES)
    sub_strand = models.ForeignKey(SubStrand, on_delete=models.CASCADE, related_name='questions')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='created_questions',
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        unique_together = ('quiz','sub_strand')
        ordering = ('quiz',)

    def __str__(self):
        return f"{self.quiz} ({self.sub_strand.name})"

class Option(models.Model):
    uuid=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    question=models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    option=models.TextField(blank=True,null=True)
    option_image=models.ImageField(
        upload_to='questions/options/%Y/%m/',
        blank=True,
        null=True,
        help_text='Optional image for visual answer choices.',
    )
    is_correct=models.BooleanField(default=False)
    is_active=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name="Option"
        verbose_name_plural="Options"
        unique_together=('question','option')
        ordering=('question',)

    def __str__(self):
        return f"{self.option} ({self.question.quiz})"

class Quiz(models.Model):
    difficulty_choice=(
        ("Easy","Easy"),
        ("Medium","Medium"),
        ("Hard","Hard"),
    )
  
    uuid=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    title=models.CharField(max_length=100)
    description=models.TextField(blank=True,null=True)
    difficulty=models.CharField(max_length=50,choices=difficulty_choice)
    subject=models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='quizzes',null=True,blank=True)
    strand=models.ForeignKey(Strand, on_delete=models.CASCADE, related_name='quizzes',null=True,blank=True)
    sub_strand = models.ForeignKey(SubStrand, on_delete=models.CASCADE, related_name='quizzes',null=True,blank=True)
    questions=models.ManyToManyField(Question, related_name='quizzes')
    is_active = models.BooleanField(default=True)
    test_size=models.IntegerField(default=0)
    time_limit_minutes=models.PositiveIntegerField(
        default=0,
        help_text='Exam duration in minutes. 0 means no time limit.',
    )
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='quizzes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Quiz"
        verbose_name_plural = "Quizzes"
        unique_together = ('title','sub_strand')
        ordering = ('title',)

    def __str__(self):
        return f"{self.title} ({self.sub_strand.name})"

class UserAttempts(models.Model):
    uuid=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    user=models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attempts')
    student=models.ForeignKey('accounts.Student', on_delete=models.CASCADE, related_name='attempts')
    quiz=models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    score=models.IntegerField(default=0)
    marks_earned=models.IntegerField(default=0)
    marks_possible=models.IntegerField(default=0)
    answers=models.JSONField(default=dict, blank=True)
    is_active=models.BooleanField(default=True)
    is_complete=models.BooleanField(default=False)
    attempt_number = models.PositiveIntegerField(
        default=1,
        help_text='Sequential attempt number for this student + quiz pair. 1 = first try, 2 = first retake, etc.',
    )
    started_at=models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the current in-progress attempt clock started.',
    )
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name="User Attempt"
        verbose_name_plural="User Attempts"
        # One row per student+quiz+attempt_number — multiple attempts are allowed.
        unique_together=('student', 'quiz', 'attempt_number')
        ordering=('-created_at',)


class AttemptResponse(models.Model):
    GRADED_BY_CHOICES = (
        ('auto', 'Auto'),
        ('teacher', 'Teacher'),
        ('ai', 'AI'),
    )

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(
        UserAttempts, on_delete=models.CASCADE, related_name='responses',
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name='attempt_responses',
    )
    selected_option = models.ForeignKey(
        Option, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='attempt_responses',
    )
    text_answer = models.TextField(blank=True)
    marks_awarded = models.IntegerField(default=0)
    max_marks = models.IntegerField(default=1)
    is_correct = models.BooleanField(null=True, blank=True)
    graded_by = models.CharField(max_length=20, choices=GRADED_BY_CHOICES, default='auto')
    answered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Attempt Response'
        verbose_name_plural = 'Attempt Responses'
        unique_together = ('attempt', 'question')
        ordering = ('answered_at',)

    def __str__(self):
        return f'{self.attempt_id} — {self.question_id}'
