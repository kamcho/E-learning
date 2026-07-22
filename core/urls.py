from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path(
        'tests/<uuid:quiz_uuid>/learners/<uuid:student_uuid>/info/',
        views.test_info_view,
        name='test_info',
    ),
    path(
        'tests/<uuid:quiz_uuid>/learners/<uuid:student_uuid>/take/',
        views.test_take_view,
        name='test_take',
    ),
    path(
        'tests/<uuid:quiz_uuid>/learners/<uuid:student_uuid>/result/',
        views.attempt_detail_view,
        name='attempt_detail',
    ),
    path(
        'attempts/<uuid:attempt_uuid>/',
        views.attempt_by_uuid_view,
        name='attempt_by_uuid',
    ),
    path('api/ai/explain-answer/', views.ai_explain_answer_view, name='ai_explain_answer'),
    path('exams/', views.exams_list_view, name='exams_list'),
    path('exams/<uuid:quiz_uuid>/analytics/', views.exam_analytics_view, name='exam_analytics'),
    # Quiz Builder (teachers + admin)
    path('quizzes/', views.quiz_builder_list_view, name='quiz_builder_list'),
    path('quizzes/create/', views.quiz_create_view, name='quiz_create'),
    path('quizzes/<uuid:quiz_uuid>/edit/', views.quiz_edit_view, name='quiz_edit'),
    path('quizzes/<uuid:quiz_uuid>/delete/', views.quiz_delete_view, name='quiz_delete'),
    path('api/quiz-questions/', views.quiz_questions_api_view, name='quiz_questions_api'),
    path('questions/bulk-import/', views.bulk_question_import_view, name='bulk_question_import'),
    path('api/questions/bulk/', views.bulk_create_questions_api_view, name='bulk_create_questions_api'),
    path('api/exam-filters/', views.exam_filter_options_api_view, name='exam_filter_options_api'),
]
