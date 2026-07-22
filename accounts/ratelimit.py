"""Simple cache-backed rate limiting for auth and API endpoints."""

from functools import wraps

from django.contrib import messages
from django.core.cache import cache
from django.http import JsonResponse

from .auth_utils import get_client_ip


def _cache_incr(key, window_seconds):
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, window_seconds)
        return 1


def is_rate_limited(key, limit, window_seconds):
    if limit <= 0:
        return False
    count = _cache_incr(key, window_seconds)
    return count > limit


def check_rate_limits(limits):
    """
    limits: list of (key, limit, window_seconds) tuples.
    Returns the first exceeded limit key, or None.
    """
    for key, limit, window in limits:
        if is_rate_limited(key, limit, window):
            return key
    return None


def rate_limit(*, key, limit, window, by='ip', methods=None, json_error='Too many requests. Please try again later.'):
    """Decorator for views that should return JSON on throttle."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if methods and request.method not in methods:
                return view_func(request, *args, **kwargs)

            identifier = _identifier(request, by)
            cache_key = f'rl:{key}:{identifier}'
            if is_rate_limited(cache_key, limit, window):
                return JsonResponse({'ok': False, 'error': json_error}, status=429)

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def _identifier(request, by):
    if by == 'user':
        if request.user.is_authenticated:
            return f'user:{request.user.pk}'
        return f'ip:{get_client_ip(request)}'
    if by == 'phone':
        phone = ''
        if request.method == 'POST':
            phone = (request.POST.get('phone') or '').strip()
        return f'phone:{phone or "unknown"}'
    return f'ip:{get_client_ip(request)}'


def throttle_login_attempt(request, phone=''):
    """Apply sign-in rate limits. Returns an error message if blocked."""
    ip = get_client_ip(request)
    limits = [
        (f'rl:signin:ip:{ip}', 15, 15 * 60),
    ]
    if phone:
        limits.append((f'rl:signin:phone:{phone}', 8, 15 * 60))
    if check_rate_limits(limits):
        return 'Too many sign-in attempts. Please wait 15 minutes and try again.'
    return None


def throttle_google_auth(request):
    ip = get_client_ip(request)
    if check_rate_limits([(f'rl:google:ip:{ip}', 20, 15 * 60)]):
        return 'Too many Google sign-in attempts. Please wait and try again.'
    return None
