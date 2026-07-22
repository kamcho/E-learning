from django.urls import path
from . import views

app_name = 'subjects'

urlpatterns = [
    # Grade Levels
    path('grade-levels/', views.grade_level_list, name='grade_level_list'),
    path('grade-levels/<slug:slug>/', views.grade_level_detail, name='grade_level_detail'),

    # Disciplines
    path('disciplines/', views.discipline_list, name='discipline_list'),
    path('disciplines/<slug:slug>/', views.discipline_detail, name='discipline_detail'),

    # Subjects
    path('subjects/', views.subject_list, name='subject_list'),
    path('subjects/<slug:slug>/', views.subject_detail, name='subject_detail'),

    # Strands
    path('strands/<slug:slug>/', views.strand_detail, name='strand_detail'),

    # SubStrands
    path('sub-strands/<slug:slug>/', views.sub_strand_detail, name='sub_strand_detail'),

    # Questions (subject-level)
    path('questions/create/<int:subject_id>/', views.create_question_for_subject, name='create_question'),
]
