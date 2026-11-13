from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse

from .audit import clear_current_request, set_current_request
from .auth_utils import user_needs_phone_link

# URL names that must stay reachable without a linked phone number.
_PHONE_LINK_EXEMPT_URL_NAMES = {
    'complete_profile',
    'signout',
    'google_auth',
    'signin',
    'signup',
    'totp_verify',
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


class CurrentRequestMiddleware:
    """Expose the active request to audit signal handlers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_request(request)
        try:
            return self.get_response(request)
        finally:
            clear_current_request()


_TWO_FACTOR_EXEMPT_URL_NAMES = {
    'signin',
    'signup',
    'signout',
    'google_auth',
    'totp_verify',
    'password_reset',
    'password_reset_done',
    'password_reset_confirm',
    'password_reset_complete',
    'complete_profile',
}


class TwoFactorMiddleware:
    """Block sessions that have not completed TOTP when 2FA is enabled."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            from .totp import is_2fa_verified_for_user, user_has_totp_enabled

            if user_has_totp_enabled(user) and not is_2fa_verified_for_user(request, user):
                resolver = request.resolver_match
                if resolver and resolver.app_name == 'accounts':
                    if resolver.url_name in _TWO_FACTOR_EXEMPT_URL_NAMES:
                        return self.get_response(request)
                    if resolver.url_name == 'account_security':
                        return self.get_response(request)
                return redirect(
                    f"{reverse('accounts:totp_verify')}?{urlencode({'reason': 'required'})}"
                )

        return self.get_response(request)

