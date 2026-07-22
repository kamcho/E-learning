from django.core.exceptions import ValidationError


def _validate_upload_size(upload, max_bytes, label):
    if upload.size > max_bytes:
        mb = max_bytes // (1024 * 1024)
        raise ValidationError(f'{label} must be {mb} MB or smaller.')


def validate_question_image(upload):
    allowed = {
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
    }
    content_type = getattr(upload, 'content_type', '') or ''
    if content_type and content_type not in allowed:
        raise ValidationError('Upload a JPEG, PNG, GIF, or WebP image.')
    _validate_upload_size(upload, 5 * 1024 * 1024, 'Image')


def validate_question_audio(upload):
    allowed = {
        'audio/mpeg',
        'audio/mp3',
        'audio/wav',
        'audio/x-wav',
        'audio/ogg',
        'audio/webm',
        'audio/mp4',
        'audio/aac',
    }
    content_type = getattr(upload, 'content_type', '') or ''
    if content_type and content_type not in allowed:
        raise ValidationError('Upload an MP3, WAV, OGG, or AAC audio file.')
    _validate_upload_size(upload, 10 * 1024 * 1024, 'Audio file')


def validate_option_image(upload):
    validate_question_image(upload)
