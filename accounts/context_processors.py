from .models import Role


def account_nav(request):
    if not request.user.is_authenticated:
        return {}
    return {
        'role_choices': Role.choices,
        'can_switch_role': request.user.is_superuser,
    }
