from django.contrib import admin
from .models import AttemptResponse, Question, Option, Quiz, UserAttempts


class OptionInline(admin.TabularInline):
    model = Option
    extra = 2


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'sub_strand', 'difficulty', 'quiz_type', 'created_by', 'has_prompt_image', 'is_active')
    list_filter = ('difficulty', 'quiz_type', 'is_active', 'sub_strand', 'created_by')
    search_fields = ('quiz', 'image_alt_text')
    inlines = [OptionInline]

    @admin.display(boolean=True, description='Image')
    def has_prompt_image(self, obj):
        return bool(obj.prompt_image)


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
