"""Helpers for switching the authenticated user's platform role."""

from django.urls import reverse

from .models import Role

VALID_ROLES = {choice[0] for choice in Role.choices}


def role_label(role_value):
    return dict(Role.choices).get(role_value, role_value.replace('_', ' ').title())


def redirect_path_for_role(user):
    """Default landing page after a role change."""
    if user.is_platform_admin:
        return reverse('accounts:admin_dashboard')
    if user.is_guardian:
        return reverse('accounts:guardian_dashboard')
    if user.is_teacher:
        return reverse('accounts:teacher_dashboard')
    if user.is_referral:
        return reverse('accounts:referral_dashboard')
    if user.is_staff:
        return reverse('accounts:admin_dashboard')
    return reverse('core:landing')
