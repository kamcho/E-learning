from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import (
    AIExplanation,
    ApplicationErrorLog,
    AttemptResponse,
    GuestDemoAttempt,
    Question,
    Option,
    Quiz,
    UserAttempts,
)


@admin.register(ApplicationErrorLog)
class ApplicationErrorLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'status_code', 'method', 'path', 'user_label', 'exception_type', 'is_resolved')
    list_filter = ('status_code', 'is_resolved', 'created_at')
    search_fields = ('path', 'user_label', 'user__phone', 'message', 'exception_type', 'reference')
    readonly_fields = (
        'reference', 'status_code', 'method', 'path', 'user', 'user_label', 'user_agent',
        'source', 'exception_type', 'message', 'traceback', 'created_at',
    )
    ordering = ('-created_at',)


class OptionInline(admin.TabularInline):
    model = Option
    extra = 2


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        'quiz', 'sub_strand', 'difficulty', 'quiz_type', 'created_by',
        'has_prompt_image', 'has_tts_prompt_audio', 'is_active',
    )
    list_filter = ('difficulty', 'quiz_type', 'is_active', 'sub_strand', 'created_by')
    search_fields = ('quiz', 'image_alt_text')
    readonly_fields = ('tts_prompt_audio', 'tts_prompt_voice', 'tts_prompt_text_hash')
    inlines = [OptionInline]

    @admin.display(boolean=True, description='Image')
    def has_prompt_image(self, obj):
        return bool(obj.prompt_image)

    @admin.display(boolean=True, description='Generated read-aloud')
    def has_tts_prompt_audio(self, obj):
        return bool(obj.tts_prompt_audio)


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ('option', 'question', 'is_correct', 'has_option_image', 'is_active')

    @admin.display(boolean=True, description='Image')
    def has_option_image(self, obj):
        return bool(obj.option_image)
    list_filter = ('is_correct', 'is_active')
    search_fields = ('option',)


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'strand', 'difficulty', 'is_active', 'created_by')
    list_filter = ('difficulty', 'is_active', 'subject')
    search_fields = ('title', 'description')
    filter_horizontal = ('questions',)


class AttemptResponseInline(admin.TabularInline):
    model = AttemptResponse
    extra = 0
    readonly_fields = ('question', 'marks_awarded', 'max_marks', 'is_correct', 'answered_at')
    can_delete = False


@admin.register(UserAttempts)
class UserAttemptsAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'student', 'quiz', 'score', 'marks_earned', 'marks_possible',
        'is_complete', 'created_at',
    )
    list_filter = ('is_complete', 'is_active')
    search_fields = ('user__phone', 'user__first_name', 'quiz__title')
    inlines = [AttemptResponseInline]


@admin.register(AttemptResponse)
class AttemptResponseAdmin(admin.ModelAdmin):
    list_display = (
        'attempt', 'question', 'marks_awarded', 'max_marks', 'is_correct', 'graded_by',
    )
    list_filter = ('is_correct', 'graded_by')


@admin.register(GuestDemoAttempt)
class GuestDemoAttemptAdmin(admin.ModelAdmin):
    list_display = (
        'started_at', 'phone_number', 'grade_name', 'subject_name', 'topic_label', 'status',
        'answered_count', 'question_count', 'score', 'linked_payment',
    )
    list_filter = ('status', 'grade_name', 'started_at')
    search_fields = ('phone_number', 'demo_id', 'subject_name', 'topic_label')
    readonly_fields = (
        'uuid', 'demo_id', 'phone_number', 'grade_name', 'subject_name', 'scope_label',
        'topic_label', 'question_ids', 'answers', 'feedback', 'question_count',
        'correct_count', 'marks_earned', 'marks_possible', 'score', 'status',
        'started_at', 'completed_at', 'updated_at',
    )
    fields = readonly_fields
    ordering = ('-started_at',)

    @admin.display(description='Guest payment')
    def linked_payment(self, obj):
        from subscriptions.models import GuestDemoPayment

        payment = GuestDemoPayment.objects.filter(demo_id=obj.demo_id).only(
            'uuid', 'status', 'amount_kes',
        ).first()
        if not payment:
            return '—'
        url = reverse('admin:subscriptions_guestdemopayment_change', args=[payment.pk])
        return format_html(
            '<a href="{}">{} · KES {}</a>',
            url,
            payment.get_status_display(),
            payment.amount_kes,
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AIExplanation)
class AIExplanationAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'question', 'selected_option', 'selected_answer', 'tts_voice', 'model')
    list_filter = ('model', 'tts_voice', 'created_at')
    search_fields = ('explanation', 'selected_answer', 'lookup_key', 'question__quiz')
    readonly_fields = (
        'uuid', 'question', 'lookup_key', 'selected_option', 'selected_answer',
        'explanation', 'correct_answer', 'tts_audio', 'tts_voice',
        'prompt_snapshot', 'model', 'created_at',
    )
    def has_add_permission(self, request):
        return False
