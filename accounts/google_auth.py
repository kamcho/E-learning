from django.conf import settings
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .models import MyUser, Role


class GoogleAuthError(Exception):
    pass


def get_google_client_ids():
    """Return configured Google OAuth Web client IDs."""
    if hasattr(settings, 'GOOGLE_CLIENT_ID') and not settings.GOOGLE_CLIENT_ID:
        return []
    ids = list(getattr(settings, 'GOOGLE_CLIENT_IDS', []) or [])
    if not ids and getattr(settings, 'GOOGLE_CLIENT_ID', ''):
        ids = [item.strip() for item in settings.GOOGLE_CLIENT_ID.split(',') if item.strip()]
    return ids


def verify_google_credential(credential):
    """Verify a Google Identity Services ID token and return the token claims."""
    client_ids = get_google_client_ids()
    if not client_ids:
        raise GoogleAuthError('Google Sign-In is not configured.')

    try:
        idinfo = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            client_ids[0] if len(client_ids) == 1 else client_ids,
        )
    except ValueError as exc:
        raise GoogleAuthError('Invalid Google sign-in token.') from exc

    audience = idinfo.get('aud')
    if audience not in client_ids:
        raise GoogleAuthError('Google token audience mismatch.')

    if not idinfo.get('email_verified'):
        raise GoogleAuthError('Google email address is not verified.')

    return idinfo


def get_or_create_user_from_google(idinfo):
    """Find, link, or create a platform user from verified Google token claims."""
    google_id = idinfo['sub']
    email = (idinfo.get('email') or '').strip()
    first_name = (idinfo.get('given_name') or '').strip()
    last_name = (idinfo.get('family_name') or '').strip()

    user = MyUser.objects.filter(google_id=google_id).first()
    if user:
        return user, False

    if email:
        user = MyUser.objects.filter(email__iexact=email).first()
        if user:
            if user.google_id and user.google_id != google_id:
                raise GoogleAuthError('This email is linked to a different Google account.')
            user.google_id = google_id
            if not user.first_name and first_name:
                user.first_name = first_name
            if not user.last_name and last_name:
                user.last_name = last_name
            user.save(update_fields=['google_id', 'first_name', 'last_name', 'updated_at'])
            return user, False

    user = MyUser(
        google_id=google_id,
        email=email or None,
        first_name=first_name or 'Google',
        last_name=last_name or 'User',
        role=Role.GUARDIAN,
    )
    user.set_unusable_password()
    user.save()
    return user, True
