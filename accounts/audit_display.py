"""Presentation helpers for the admin action log UI."""

from django.db.models import Q


def initials_from_label(label):
    if not label or label == 'anonymous':
        return '?'
    parts = [p for p in str(label).replace('·', ' ').split() if p.strip()]
    if not parts:
        return '?'
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


def category_for_log(log):
    """Return (label, css_slug) for filter + badge."""
    action = (log.action or '').lower()
    object_type = (log.object_type or '').lower()

    if action.startswith('auth.'):
        return 'AUTHENTICATION', 'auth'
    if 'backup' in action or 'database' in action:
        return 'SYSTEM CONFIGURATION', 'system'
    if object_type.startswith('subscriptions.') or 'payment' in object_type:
        return 'BILLING', 'billing'
    if object_type.startswith('subjects.') or 'curriculum' in action:
        return 'CURRICULUM', 'curriculum'
    if object_type.startswith('core.question') or object_type.startswith('core.option'):
        return 'QUESTION BANK', 'content'
    if object_type.startswith('core.'):
        return 'ASSESSMENTS', 'assessments'
    if object_type.startswith('accounts.student'):
        return 'LEARNERS', 'learners'
    if object_type.startswith('accounts.'):
        return 'USER ACCOUNTS', 'accounts'
    meta = log.metadata if isinstance(log.metadata, dict) else {}
    if meta.get('source') == 'http_middleware':
        return 'HTTP REQUEST', 'http'
    return 'GENERAL', 'general'


def action_label_for_log(log):
    verb = log.verb or 'request'
    labels = {
        'create': 'Created',
        'update': 'Updated',
        'delete': 'Deleted',
        'login': 'Signed in',
        'logout': 'Signed out',
        'request': 'Requested',
        'view': 'Viewed',
    }
    if verb in labels:
        return labels[verb]
    if log.request_method:
        return log.request_method
    return verb.replace('_', ' ').title()


def description_for_log(log):
    meta = log.metadata if isinstance(log.metadata, dict) else {}
    verb = log.verb
    obj_name = (log.object_repr or '').strip()
    type_short = ''
    if log.object_type:
        type_short = log.object_type.split('.')[-1]

    if verb == 'login':
        return 'User signed in to the platform.'
    if verb == 'logout':
        return 'User signed out.'
    if verb == 'create' and obj_name:
        return f'Created {type_short}: {obj_name}'[:500]
    if verb == 'update' and obj_name:
        detail = meta.get('m2m_action')
        if detail:
            return f'Updated linked learners ({detail}).'
        return f'Updated {type_short}: {obj_name}'[:500]
    if verb == 'delete' and obj_name:
        return f'Deleted {type_short}: {obj_name}'[:500]
    if log.request_path and meta.get('source') == 'http_middleware':
        code = f' (HTTP {log.status_code})' if log.status_code else ''
        return f'{log.request_method or "POST"} {log.request_path}{code}'[:500]
    if obj_name:
        return f'{type_short}: {obj_name}'[:500]
    if log.request_path:
        return log.request_path[:500]
    return log.action or '—'


def target_for_log(log):
    if not log.object_type and not log.object_id:
        if log.request_path:
            return 'Route', log.request_path.strip('/').split('/')[-1] or '—'
        return '', ''
    label = log.object_type.split('.')[-1] if log.object_type else 'Object'
    target_id = log.object_id or '—'
    return label.replace('_', ' ').title(), target_id


def enrich_log_row(log):
    category_label, category_slug = category_for_log(log)
    target_label, target_id = target_for_log(log)
    return {
        'log': log,
        'initials': initials_from_label(log.actor_label),
        'category_label': category_label,
        'category_slug': category_slug,
        'action_label': action_label_for_log(log),
        'description': description_for_log(log),
        'target_label': target_label,
        'target_id': target_id,
    }


def filter_queryset_by_category(qs, slug):
    """Approximate category_for_log() rules at the database layer."""
    if not slug:
        return qs

    if slug == 'auth':
        return qs.filter(action__istartswith='auth.')
    if slug == 'system':
        return qs.filter(Q(action__icontains='backup') | Q(action__icontains='database'))
    if slug == 'billing':
        return qs.filter(
            Q(object_type__istartswith='subscriptions.')
            | Q(object_type__icontains='payment')
        )
    if slug == 'curriculum':
        return qs.filter(
            Q(object_type__istartswith='subjects.')
            | Q(action__icontains='curriculum')
        )
    if slug == 'content':
        return qs.filter(
            Q(object_type__istartswith='core.question')
            | Q(object_type__istartswith='core.option')
        )
    if slug == 'assessments':
        return qs.filter(object_type__istartswith='core.').exclude(
            Q(object_type__istartswith='core.question')
            | Q(object_type__istartswith='core.option')
        )
    if slug == 'learners':
        return qs.filter(object_type__istartswith='accounts.student')
    if slug == 'accounts':
        return qs.filter(object_type__istartswith='accounts.').exclude(
            object_type__istartswith='accounts.student'
        )
    if slug == 'http':
        return qs.filter(metadata__source='http_middleware')
    if slug == 'general':
        known = (
            Q(action__istartswith='auth.')
            | Q(action__icontains='backup')
            | Q(action__icontains='database')
            | Q(object_type__istartswith='subscriptions.')
            | Q(object_type__icontains='payment')
            | Q(object_type__istartswith='subjects.')
            | Q(action__icontains='curriculum')
            | Q(object_type__istartswith='core.')
            | Q(object_type__istartswith='accounts.')
            | Q(metadata__source='http_middleware')
        )
        return qs.exclude(known)
    return qs


LOG_CATEGORY_CHOICES = [
    ('auth', 'AUTHENTICATION'),
    ('system', 'SYSTEM CONFIGURATION'),
    ('billing', 'BILLING'),
    ('curriculum', 'CURRICULUM'),
    ('content', 'QUESTION BANK'),
    ('assessments', 'ASSESSMENTS'),
    ('learners', 'LEARNERS'),
    ('accounts', 'USER ACCOUNTS'),
    ('http', 'HTTP REQUEST'),
    ('general', 'GENERAL'),
]
