"""Public error pages used when DEBUG is False."""

import sys
import traceback
from datetime import timezone as datetime_timezone
from uuid import uuid4

from django.http import HttpResponseServerError
from django.shortcuts import render
from django.template import loader
from django.utils import timezone


def _error_page(request, *, status, code, title, message, hint):
    return render(
        request,
        'errors/error.html',
        {
            'code': code,
            'title': title,
            'message': message,
            'hint': hint,
        },
        status=status,
    )


def bad_request(request, exception):
    return _error_page(
        request,
        status=400,
        code='400',
        title='Bad request',
        message='We could not understand that request.',
        hint='Go back and try again, or return home.',
    )


def permission_denied(request, exception):
    return _error_page(
        request,
        status=403,
        code='403',
        title='Access denied',
        message='You do not have permission to view this page.',
        hint='Sign in with the right account, or return home.',
    )


def page_not_found(request, exception):
    return _error_page(
        request,
        status=404,
        code='404',
        title='Page not found',
        message='That page does not exist, or it may have moved.',
        hint='Check the address, or head back to Soma Smart.',
    )


def server_error(request):
    """
    Render without request context so a broken context processor
    cannot turn this page into another 500.
    """
    report = None
    user = getattr(request, '_cached_user', None)
    exc_info = sys.exc_info()
    if (
        user is not None
        and user.is_authenticated
        and user.is_platform_admin
        and exc_info[0] is not None
    ):
        report = '\n'.join((
            f'Soma Smart error report {uuid4()}',
            f'Time: {timezone.now().astimezone(datetime_timezone.utc).isoformat()}',
            f'Path: {request.path}',
            '',
            ''.join(traceback.format_exception(*exc_info)).rstrip(),
        ))

    template = loader.get_template('errors/error.html')
    html = template.render({
        'code': '500',
        'title': 'Something went wrong',
        'message': 'We hit a problem on our side. Please try again in a moment.',
        'hint': 'If this keeps happening, go back home and try again.',
        'diagnostic_report': report,
    })
    return HttpResponseServerError(html)
