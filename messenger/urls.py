from django.urls import path

from .views import whatsapp_support_webhook

app_name = 'messenger'

urlpatterns = [
    path('whatsapp/webhook/', whatsapp_support_webhook, name='whatsapp_support_webhook'),
]
