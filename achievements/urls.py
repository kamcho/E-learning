from django.urls import path

from . import views

app_name = 'achievements'

urlpatterns = [
    path('', views.achievement_list, name='achievement_list'),
    path('create/', views.achievement_create, name='achievement_create'),
]
