"""Collapse bulk question-bank creates into single list rows (DB rows stay separate)."""

from collections import defaultdict

from accounts.audit_display import enrich_log_row

GROUPABLE_OBJECT_TYPES = frozenset({'core.Question', 'core.Option'})
GROUP_TIME_WINDOW_SEC = 30
MAX_LOGS_FOR_GROUPING = 4000


def is_groupable_log(log):
    if log.verb != 'create':
        return False
    return (log.object_type or '') in GROUPABLE_OBJECT_TYPES


def _cluster_key(log):
    return (log.user_id, log.action, log.verb, log.object_type)


def _cluster_groupable_logs(groupable_logs):
    """Merge same actor/action/type creates within a short time window."""
    buckets = defaultdict(list)
    for log in groupable_logs:
        buckets[_cluster_key(log)].append(log)

    clusters = []
    for key, members in buckets.items():
        members.sort(key=lambda row: row.created_at, reverse=True)
        current = []
        anchor_ts = None
        for log in members:
            ts = log.created_at.timestamp()
            if anchor_ts is None or abs(anchor_ts - ts) <= GROUP_TIME_WINDOW_SEC:
                if anchor_ts is None:
                    anchor_ts = ts
                current.append(log)
            else:
                if current:
                    clusters.append(current)
                current = [log]
                anchor_ts = ts
        if current:
            clusters.append(current)
    return clusters


def description_for_batch(members):
    type_short = 'records'
    if members and members[0].object_type:
        type_short = members[0].object_type.split('.')[-1]
    count = len(members)
    plural = type_short if count == 1 else f'{type_short}s'
    return f'Bulk operation: created {count} {plural} in one batch.'


def build_activity_display_items(logs_qs):
    """
    Return display items sorted newest-first. Each item is either single or batch.
    """
    logs = list(logs_qs[:MAX_LOGS_FOR_GROUPING])
    groupable = [row for row in logs if is_groupable_log(row)]
    standalone = [row for row in logs if not is_groupable_log(row)]

    items = []
    for log in standalone:
        items.append({
            'kind': 'single',
            'created_at': log.created_at,
            'log_id': log.pk,
            'log_ids': [log.pk],
            'row': enrich_log_row(log),
        })

    for members in _cluster_groupable_logs(groupable):
        if len(members) == 1:
            log = members[0]
            items.append({
                'kind': 'single',
                'created_at': log.created_at,
                'log_id': log.pk,
                'log_ids': [log.pk],
                'row': enrich_log_row(log),
            })
            continue

        members.sort(key=lambda row: row.created_at, reverse=True)
        representative = members[0]
        row = enrich_log_row(representative)
        row['description'] = description_for_batch(members)
        row['target_label'] = row['target_label'] or 'Question'
        row['target_id'] = f'{len(members)} items'
        items.append({
            'kind': 'batch',
            'created_at': max(member.created_at for member in members),
            'log_id': representative.pk,
            'log_ids': [member.pk for member in members],
            'count': len(members),
            'row': row,
            'members': members,
        })

    items.sort(key=lambda item: item['created_at'], reverse=True)
    return items


def detail_ids_query(log_ids):
    return ','.join(str(pk) for pk in log_ids)
