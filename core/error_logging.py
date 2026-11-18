"""Persist application log records and failed HTTP responses for staff review."""

import logging
import re
import traceback

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.utils import timezone


_SENSITIVE_VALUE = re.compile(
    r'(?i)([\"\']?(?:authorization|password|passwd|pin|secret|api[_-]?key|access[_-]?token|'
    r'refresh[_-]?token|consumer[_-]?secret|passkey)[\"\']?\s*[:=]\s*)'
    r'([\"\']?)([^\s,;\"\']+)'
)


def _redact(value):
    value = value or ''
    return _SENSITIVE_VALUE.sub(r'\1[REDACTED]', str(value))


def _request_user(request):
    try:
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            return user
    except Exception:
        pass
    return None


def persist_error(*, request=None, status_code=500, source='', exception=None, message='', trace=''):
    """Save an error safely; logging failures must never break the request being served."""
    try:
        from core.models import ApplicationErrorLog

        if request is not None and getattr(request, '_application_error_log_reference', None):
            return None

        user = _request_user(request) if request is not None else None
        row = ApplicationErrorLog.objects.create(
            status_code=max(400, min(int(status_code or 500), 599)),
            method=(getattr(request, 'method', '') if request is not None else '')[:10],
            # Query strings and request bodies are deliberately excluded: they often contain
            # credentials, reset tokens, payment identifiers, or learner answers.
            path=(getattr(request, 'path', '') if request is not None else '')[:512],
            user=user,
            user_label=(getattr(user, 'full_name', '') if user else '')[:120],
            user_agent=(request.META.get('HTTP_USER_AGENT', '') if request is not None else '')[:512],
            source=(source or '')[:160],
            exception_type=(type(exception).__name__ if exception else '')[:255],
            message=_redact(message)[:8000],
            traceback=_redact(trace)[:24000],
        )
        if request is not None:
            request._application_error_log_reference = str(row.reference)
        return row
    except Exception:
        # Do not log through Python logging here; this function is itself the log sink.
        return None


class DatabaseErrorHandler(logging.Handler):
    """Store ERROR+ log records, including caught exceptions with HTTP request context."""

    def emit(self, record):
        try:
            from accounts.audit import get_current_request

            request = getattr(record, 'request', None) or get_current_request()
            if request is not None and getattr(request, '_application_error_log_reference', None):
                return
            exception = record.exc_info[1] if record.exc_info else None
            trace = ''.join(traceback.format_exception(*record.exc_info)) if record.exc_info else ''
            message = record.getMessage()
            persist_error(
                request=request,
                status_code=getattr(record, 'status_code', None) or 500,
                source=record.name,
                exception=exception,
                message=message,
                trace=trace,
            )
        except Exception:
            # Error persistence is best-effort when the database or logging subsystem fails.
            return


class ErrorLogMiddleware:
    """Record unhandled exceptions and failed HTTP responses without storing request secrets."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code >= 400:
            persist_error(
                request=request,
                status_code=response.status_code,
                source='http.response',
                message=getattr(response, 'reason_phrase', '') or 'HTTP request failed',
            )
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, Http404):
            status_code = 404
        elif isinstance(exception, PermissionDenied):
            status_code = 403
        elif isinstance(exception, SuspiciousOperation):
            status_code = 400
        else:
            status_code = 500
        trace = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        row = persist_error(
            request=request,
            status_code=status_code,
            source='django.request',
            exception=exception,
            message=str(exception) or type(exception).__name__,
            trace=trace,
        )
        if row:
            request._application_error_log_reference = str(row.reference)
        return None
