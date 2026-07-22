from django.shortcuts import redirect
from django.urls import reverse

from .auth_utils import user_needs_phone_link

# URL names that must stay reachable without a linked phone number.
_PHONE_LINK_EXEMPT_URL_NAMES = {
    'complete_profile',
    'signout',
    'google_auth',
    'signin',
    'signup',
    'password_reset',
    'password_reset_done',
    'password_reset_confirm',
    'password_reset_complete',
}


class GooglePhoneLinkMiddleware:
    """Send Google-only accounts to link a phone number and PIN."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated or not user_needs_phone_link(request.user):
            return self.get_response(request)

        resolver = request.resolver_match
        if resolver is None:
            return self.get_response(request)

        url_name = resolver.url_name
        app_name = resolver.app_name
        if app_name == 'accounts' and url_name in _PHONE_LINK_EXEMPT_URL_NAMES:
            return self.get_response(request)

        return redirect('accounts:complete_profile')
