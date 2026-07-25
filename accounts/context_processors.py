from django.conf import settings

from .models import Role


def account_nav(request):
    if not request.user.is_authenticated:
        return {}
    return {
        'role_choices': Role.choices,
        'can_switch_role': request.user.is_superuser,
    }


def google_auth(request):
    client_ids = getattr(settings, 'GOOGLE_CLIENT_IDS', [])
    primary_client_id = client_ids[0] if client_ids else ''
    return {
        'google_client_id': primary_client_id,
        'google_signin_enabled': bool(primary_client_id),
    }
