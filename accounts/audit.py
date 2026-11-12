"""User action audit logging."""

import threading

from accounts.auth_utils import get_client_ip
from accounts.models import MyUser, UserActionLog

_request_local = threading.local()

SENSITIVE_FORM_KEYS = frozenset({
    'password',
    'password1',
    'password2',
    'pin',
    'old_password',
    'new_password',
    'csrfmiddlewaretoken',
})

SKIP_AUDIT_PATH_PREFIXES = (
    '/static/',
    '/media/',
    '/favicon.ico',
)


def set_current_request(request):
    _request_local.request = request


def get_current_request():
    return getattr(_request_local, 'request', None)


def clear_current_request():
    if hasattr(_request_local, 'request'):
        del _request_local.request


def actor_label_for_user(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return 'anonymous'
    name = getattr(user, 'full_name', '') or ''
    parts = [name.strip(), getattr(user, 'phone', '') or getattr(user, 'email', '')]
    label = ' · '.join(part for part in parts if part)
    return label[:120] or f'user:{user.pk}'


def object_ref_for_instance(instance):
    """Return (object_type, object_id, object_repr) for a model instance."""
    if instance is None:
        return '', '', ''
    model = instance.__class__
    object_type = f'{model._meta.app_label}.{model.__name__}'
    pk = getattr(instance, 'pk', None)
    object_id = '' if pk is None else str(pk)
    try:
        object_repr = str(instance)[:2000]
    except Exception:
        object_repr = object_type
    return object_type, object_id, object_repr


def log_user_action(
    *,
    action,
    verb='request',
    user=None,
    obj=None,
    request=None,
    object_type='',
    object_id='',
    object_repr='',
    status_code=None,
    metadata=None,
):
    """
    Persist one audit row. Safe to call from signals/middleware (swallows DB errors).
    """
    request = request or get_current_request()
    if user is None and request is not None and getattr(request, 'user', None):
        if request.user.is_authenticated:
            user = request.user

    if obj is not None and not object_type:
        object_type, object_id, object_repr = object_ref_for_instance(obj)
    elif obj is None and not object_repr:
        object_repr = object_repr or ''

    row = UserActionLog(
        user=user if isinstance(user, MyUser) else None,
        actor_label=actor_label_for_user(user),
        action=(action or '')[:120],
        verb=verb if verb in dict(UserActionLog.VERB_CHOICES) else 'request',
        object_type=(object_type or '')[:100],
        object_id=(object_id or '')[:64],
        object_repr=object_repr or '',
        request_path='',
        request_method='',
        ip_address=None,
        status_code=status_code,
        metadata=metadata if isinstance(metadata, dict) else {},
    )

    if request is not None:
        row.request_path = (request.path or '')[:512]
        row.request_method = (request.method or '')[:10]
        try:
            ip = get_client_ip(request)
            if ip and ip != 'unknown':
                row.ip_address = ip
        except Exception:
            pass

    try:
        row.save()
    except Exception:
        return None
    return row


def safe_form_summary(request):
    """Non-sensitive POST field names (values redacted when sensitive)."""
    if request is None or request.method != 'POST':
        return {}
    summary = {}
    for key in request.POST:
        if key in SENSITIVE_FORM_KEYS:
            summary[key] = '<redacted>'
        else:
            val = request.POST.get(key, '')
            summary[key] = (val[:200] + '…') if len(val) > 200 else val
    return summary


def action_code_from_request(request):
    match = getattr(request, 'resolver_match', None)
    if not match:
        return (request.path or '')[:120]
    if getattr(match, 'view_name', None):
        return str(match.view_name)[:120]
    app = match.app_name or 'root'
    return f'{app}:{match.url_name or "unknown"}'[:120]


def should_skip_request_audit(request):
    path = request.path or ''
    return any(path.startswith(prefix) for prefix in SKIP_AUDIT_PATH_PREFIXES)


def content_type_label(instance):
    return f'{instance._meta.app_label}.{instance._meta.model_name}'
