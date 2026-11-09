import os
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import closing

from django.conf import settings
from django.db import connections


def create_database_backup():
    """Return a seekable temporary stream containing a consistent DB backup."""
    database = settings.DATABASES['default']
    vendor = connections['default'].vendor
    backup_file = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024, mode='w+b')

    try:
        if vendor == 'sqlite':
            _write_sqlite_backup(backup_file)
            extension = 'sqlite3'
        elif vendor == 'postgresql':
            _write_postgres_backup(backup_file, database)
            extension = 'sql'
        else:
            raise RuntimeError(f'Database backups are not supported for {vendor}.')
        backup_file.seek(0)
        return backup_file, extension
    except Exception:
        backup_file.close()
        raise


def _write_sqlite_backup(backup_file):
    source = connections['default']
    source.ensure_connection()
    file_descriptor, backup_path = tempfile.mkstemp(suffix='.sqlite3')
    os.close(file_descriptor)

    try:
        with closing(sqlite3.connect(backup_path)) as destination:
            source.connection.backup(destination)
        with open(backup_path, 'rb') as database_file:
            shutil.copyfileobj(database_file, backup_file)
    finally:
        os.unlink(backup_path)


def _write_postgres_backup(backup_file, database):
    pg_dump = shutil.which('pg_dump')
    if not pg_dump:
        raise RuntimeError('pg_dump is not installed or is not available on the server PATH.')

    environment = os.environ.copy()
    if database.get('PASSWORD'):
        environment['PGPASSWORD'] = str(database['PASSWORD'])

    command = [pg_dump, '--no-owner', '--no-privileges']
    if database.get('HOST'):
        command.extend(['--host', str(database['HOST'])])
    if database.get('PORT'):
        command.extend(['--port', str(database['PORT'])])
    if database.get('USER'):
        command.extend(['--username', str(database['USER'])])
    command.extend(['--dbname', str(database['NAME']), '--no-password'])
    try:
        result = subprocess.run(
            command,
            env=environment,
            stdout=backup_file,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Database backup timed out after five minutes.') from exc

    if result.returncode:
        error_detail = (result.stderr or '').strip()
        raise RuntimeError(error_detail[:500] or 'pg_dump failed without an error message.')
