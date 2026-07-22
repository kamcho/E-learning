from django.urls import path

from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('plans/', views.plans_view, name='plans'),
    path('subscribe/<slug:plan_slug>/', views.subscribe_view, name='subscribe'),
    path('payments/<uuid:payment_uuid>/pending/', views.payment_pending_view, name='payment_pending'),
    path('payments/<uuid:payment_uuid>/status/', views.payment_status_view, name='payment_status'),
    path('mpesa/callback/', views.mpesa_callback_view, name='mpesa_callback'),
    path('my-subscription/', views.my_subscription_view, name='my_subscription'),
    path('admin/payments/', views.admin_payments_list_view, name='admin_payments_list'),
    path('admin/subscriptions/', views.admin_subscriptions_list_view, name='admin_subscriptions_list'),
]
