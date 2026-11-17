from django import template
from django.utils.safestring import mark_safe

from core.svg_sanitizer import sanitize_question_svg

register = template.Library()


@register.filter
def safe_question_svg(value):
    """Render only the restricted, sanitized SVG subset stored on a question."""
    try:
        return mark_safe(sanitize_question_svg(value))
    except (TypeError, ValueError):
        return ''
