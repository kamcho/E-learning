"""Read a narrowly scoped view of SSH authentication events from journald."""
import json
import re
import subprocess
from datetime import datetime

from django.utils import timezone


JOURNAL_COMMAND = (
    '/usr/bin/sudo', '-n', '/usr/bin/journalctl',
    '-u', 'ssh.service', '--since=-30d', '--lines=10000', '--output=json', '--no-pager',
)
MAX_JOURNAL_OUTPUT = 8 * 1024 * 1024

FAILURE_RE = re.compile(
    r"Failed (?P<method>password|publickey|keyboard-interactive(?:/pam)?) for "
    r"(?:(?P<invalid>invalid user) )?(?P<username>\S+) from "
    r"(?P<ip>[0-9a-fA-F:.]+) port (?P<port>\d+)"
)
SUCCESS_RE = re.compile(
    r"Accepted (?P<method>password|publickey|keyboard-interactive(?:/pam)?) for "
    r"(?P<username>\S+) from (?P<ip>[0-9a-fA-F:.]+) port (?P<port>\d+)"
)


class SSHAuditUnavailable(Exception):
    """The restricted journal command is unavailable or failed."""


def load_ssh_events():
    """Return normalized SSH auth events from the last 30 days of ssh.service."""
    try:
        result = subprocess.run(
            JOURNAL_COMMAND,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env={'LANG': 'C', 'LC_ALL': 'C', 'PATH': '/usr/bin:/bin'},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SSHAuditUnavailable('SSH log reader could not be started.') from exc

    if result.returncode != 0:
        raise SSHAuditUnavailable('SSH log access is not configured for this app service.')
    if len(result.stdout.encode('utf-8', errors='replace')) > MAX_JOURNAL_OUTPUT:
        raise SSHAuditUnavailable('SSH log output exceeded the safety limit.')

    events = []
    for line in result.stdout.splitlines():
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        message = str(record.get('MESSAGE', ''))
        match = FAILURE_RE.search(message)
        outcome = 'failed'
        if not match:
            match = SUCCESS_RE.search(message)
            outcome = 'accepted'
        if not match:
            continue

        try:
            timestamp = datetime.fromtimestamp(
                int(record['__REALTIME_TIMESTAMP']) / 1_000_000,
                tz=timezone.get_current_timezone(),
            )
        except (KeyError, TypeError, ValueError, OSError):
            continue

        events.append({
            'timestamp': timestamp,
            'outcome': outcome,
            'username': match.group('username'),
            'ip_address': match.group('ip'),
            'port': match.group('port'),
            'method': match.group('method'),
            'invalid_user': bool(match.groupdict().get('invalid')),
            'message': message,
        })
    events.sort(key=lambda event: event['timestamp'], reverse=True)
    return events
