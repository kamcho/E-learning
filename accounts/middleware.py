from django.shortcuts import redirect
from django.urls import reverse

from .audit import (
    action_code_from_request,
    clear_current_request,
    log_user_action,
    safe_form_summary,
    set_current_request,
    should_skip_request_audit,
)
from .auth_utils import user_needs_phone_link

MUTATING_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

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


class UserActionAuditMiddleware:
    """Log mutating HTTP requests (complements model-level audit signals)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if should_skip_request_audit(request):
            return response
        if request.method not in MUTATING_METHODS:
            return response

        user = request.user if request.user.is_authenticated else None
        if user is None and not request.path.startswith('/accounts/'):
            return response

        url_kwargs = {}
        match = getattr(request, 'resolver_match', None)
        if match and getattr(match, 'kwargs', None):
            url_kwargs = {k: str(v) for k, v in match.kwargs.items()}

        log_user_action(
            action=action_code_from_request(request),
            verb='request',
            user=user,
            request=request,
            status_code=getattr(response, 'status_code', None),
            metadata={
                'source': 'http_middleware',
                'url_kwargs': url_kwargs,
                'form_fields': safe_form_summary(request),
            },
        )
        return response
