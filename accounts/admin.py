from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import MyUser, Student, LinkedStudents, ReferralPointLog


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'grade_level', 'gender', 'dob')
    list_filter = ('gender', 'grade_level')
    search_fields = ('first_name', 'last_name')


@admin.register(LinkedStudents)
class LinkedStudentsAdmin(admin.ModelAdmin):
    list_display = ('user',)
    search_fields = ('user__phone', 'user__first_name')
    filter_horizontal = ('students',)


@admin.register(MyUser)
class MyUserAdmin(BaseUserAdmin):
    """Admin configuration for the custom MyUser model."""

    list_display = (
        'phone', 'email', 'first_name', 'last_name', 'county', 'role',
        'referral_code', 'referral_points', 'is_active', 'date_joined',
    )
    list_filter = ('role', 'county', 'is_active', 'is_staff', 'date_joined')
    search_fields = ('phone', 'first_name', 'last_name', 'email', 'referral_code', 'county')
    ordering = ('-date_joined',)

    # Fields shown when editing an existing user
    fieldsets = (
        (None, {'fields': ('phone', 'password', 'google_id')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'county')}),
        ('Referrals', {'fields': ('referral_code', 'referred_by', 'referral_points')}),
        ('Role & Permissions', {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important Dates', {'fields': ('last_login',)}),
    )

    # Fields shown when creating a new user via admin
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone', 'first_name', 'last_name', 'role', 'password1', 'password2'),
        }),
    )


@admin.register(ReferralPointLog)
class ReferralPointLogAdmin(admin.ModelAdmin):
    list_display = ('referrer', 'referred_user', 'points', 'payment', 'created_at')
    list_filter = ('created_at',)
    search_fields = (
        'referrer__first_name', 'referrer__last_name', 'referrer__phone',
        'referred_user__first_name', 'referred_user__last_name',
    )
    readonly_fields = ('created_at',)
