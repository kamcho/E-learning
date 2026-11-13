"""TOTP authenticator app (Google Authenticator, Authy, etc.)."""

import base64
import io

import pyotp
import qrcode
from django.core.signing import BadSignature, Signer

SIGNER_SALT = 'accounts.user.totp.v1'
SESSION_SETUP_SECRET = 'totp_setup_secret'
PENDING_2FA_USER_KEY = 'pending_2fa_user_id'
PENDING_2FA_NEXT_KEY = 'pending_2fa_next'
AUTH_2FA_PASSED_KEY = 'auth_2fa_user_id'

TOTP_ISSUER = 'Soma Smart'


def _signer():
    return Signer(salt=SIGNER_SALT)


def generate_totp_secret():
    return pyotp.random_base32()


def encrypt_totp_secret(secret):
    return _signer().sign(secret)


def decrypt_totp_secret(stored):
    if not stored:
        return ''
    try:
        return _signer().unsign(stored)
    except BadSignature:
        return ''


def account_label(user):
    if user.email:
        return user.email
    if user.phone:
        return user.phone
    return f'user-{user.pk}'


def provisioning_uri(user, secret):
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=account_label(user), issuer_name=TOTP_ISSUER)


def qrcode_data_url(uri):
    image = qrcode.make(uri)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    return f'data:image/png;base64,{encoded}'


def verify_totp_code(secret, code):
    if not secret or not code:
        return False
    normalized = str(code).strip().replace(' ', '')
    if not normalized.isdigit():
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(normalized, valid_window=1)


def user_has_totp_enabled(user):
    return bool(
        getattr(user, 'totp_enabled', False)
        and getattr(user, 'totp_secret', '')
    )


def get_user_totp_secret(user):
    return decrypt_totp_secret(getattr(user, 'totp_secret', ''))


def verify_user_totp(user, code):
    secret = get_user_totp_secret(user)
    if not secret:
        return False
    return verify_totp_code(secret, code)


def mark_2fa_verified(request, user):
    request.session[AUTH_2FA_PASSED_KEY] = str(user.pk)
    request.session.modified = True


def clear_2fa_session(request):
    for key in (
        AUTH_2FA_PASSED_KEY,
        PENDING_2FA_USER_KEY,
        PENDING_2FA_NEXT_KEY,
        SESSION_SETUP_SECRET,
    ):
        request.session.pop(key, None)
    request.session.modified = True


def is_2fa_verified_for_user(request, user):
    if not user_has_totp_enabled(user):
        return True
    return request.session.get(AUTH_2FA_PASSED_KEY) == str(user.pk)


def begin_pending_2fa(request, user, next_url=''):
    request.session[PENDING_2FA_USER_KEY] = str(user.pk)
    request.session[PENDING_2FA_NEXT_KEY] = next_url or ''
    request.session.modified = True


def pop_pending_2fa_user_id(request):
    raw = request.session.pop(PENDING_2FA_USER_KEY, None)
    request.session.modified = True
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def pending_2fa_next(request):
    return request.session.get(PENDING_2FA_NEXT_KEY, '')
