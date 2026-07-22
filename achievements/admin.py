from django.contrib import admin

from .models import Achievement, StudentAchievement


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
  list_display = ('title', 'slug', 'criteria_type', 'threshold', 'min_attempts', 'order', 'is_active')
  list_filter = ('criteria_type', 'is_active')
  search_fields = ('title', 'slug', 'description')
  prepopulated_fields = {'slug': ('title',)}


@admin.register(StudentAchievement)
class StudentAchievementAdmin(admin.ModelAdmin):
  list_display = ('student', 'achievement', 'earned_at')
  list_filter = ('achievement', 'earned_at')
  search_fields = ('student__first_name', 'student__last_name', 'achievement__title')
  readonly_fields = ('earned_at',)
