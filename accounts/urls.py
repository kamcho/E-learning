from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import PinPasswordResetForm, PinSetPasswordForm

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('signin/', views.signin_view, name='signin'),
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='accounts/password_reset_form.html',
            email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
            form_class=PinPasswordResetForm,
            success_url='/accounts/password-reset/done/',
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='accounts/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='accounts/password_reset_confirm.html',
            form_class=PinSetPasswordForm,
            success_url='/accounts/reset/done/',
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='accounts/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
    path('auth/google/', views.google_auth_view, name='google_auth'),
    path('complete-profile/', views.complete_profile_view, name='complete_profile'),
    path('signout/', views.signout_view, name='signout'),
    path('switch-role/', views.switch_role_view, name='switch_role'),
    path('dashboard/', views.guardian_dashboard_view, name='guardian_dashboard'),
    path('teacher-dashboard/', views.teacher_dashboard_view, name='teacher_dashboard'),
    path(
        'teacher-dashboard/subjects/<int:subject_id>/',
        views.teacher_subject_detail_view,
        name='teacher_subject_detail',
    ),
    path(
        'teacher-dashboard/questions/<uuid:question_uuid>/',
        views.teacher_question_detail_view,
        name='teacher_question_detail',
    ),
    path('referral-dashboard/', views.referral_dashboard_view, name='referral_dashboard'),
    path('admin-dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('admin/users/', views.admin_users_list_view, name='admin_users_list'),
    path('admin/students/', views.admin_students_list_view, name='admin_students_list'),
    path('admin-profile/', views.admin_profile_view, name='admin_profile'),
    path('admin/users/<int:user_id>/', views.admin_user_detail_view, name='admin_user_detail'),
    path('learners/add/', views.add_learner_view, name='add_learner'),
    path('learners/<uuid:student_uuid>/analytics/', views.student_analytics_view, name='student_analytics'),
    path(
        'learners/<uuid:student_uuid>/subjects/<int:subject_id>/progress/',
        views.student_subject_progress_view,
        name='student_subject_progress',
    ),
]
