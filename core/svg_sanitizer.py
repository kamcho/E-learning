"""Restrict imported question illustrations to a small, inert SVG subset."""

import re
import xml.etree.ElementTree as ET


SVG_NS = 'http://www.w3.org/2000/svg'
MAX_SVG_LENGTH = 20000
ALLOWED_TAGS = {
    'svg', 'g', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon',
    'path', 'text', 'tspan',
}
ALLOWED_ATTRIBUTES = {
    'viewBox', 'width', 'height', 'x', 'y', 'x1', 'y1', 'x2', 'y2', 'cx', 'cy',
    'r', 'rx', 'ry', 'points', 'd', 'fill', 'stroke', 'stroke-width',
    'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'opacity',
    'fill-opacity', 'stroke-opacity', 'font-size', 'font-weight', 'font-family',
    'text-anchor', 'dominant-baseline', 'role', 'aria-label', 'aria-hidden',
}
SAFE_VALUE = re.compile(r'^[\w\s.,#%()+\-/]+$')


def sanitize_question_svg(value):
    """Return safe inline SVG markup, or an empty string for empty input."""
    value = (value or '').strip()
    if not value:
        return ''
    if len(value) > MAX_SVG_LENGTH or '<!' in value:
        raise ValueError('SVG illustration is too large or contains unsupported XML.')
    try:
        root = ET.fromstring(value)
    except ET.ParseError as exc:
        raise ValueError('SVG illustration must be valid SVG markup.') from exc

    if root.tag not in (f'{{{SVG_NS}}}svg', 'svg'):
        raise ValueError('SVG illustration must have an <svg> root element.')

    def clean_element(element, is_root=False):
        tag = element.tag.rsplit('}', 1)[-1] if isinstance(element.tag, str) else ''
        if tag not in ALLOWED_TAGS:
            raise ValueError(f'SVG element <{tag}> is not allowed.')
        cleaned = ET.Element(f'{{{SVG_NS}}}{tag}')
        for raw_name, raw_value in element.attrib.items():
            name = raw_name.rsplit('}', 1)[-1]
            if name == 'xmlns':
                continue
            if (
                name not in ALLOWED_ATTRIBUTES
                or not SAFE_VALUE.fullmatch(raw_value)
                or 'url(' in raw_value.lower()
            ):
                raise ValueError(f'SVG attribute "{name}" is not allowed.')
            if name in ('width', 'height') and not re.fullmatch(r'\d+(?:\.\d+)?(?:px)?', raw_value.strip()):
                raise ValueError(f'SVG {name} must be a pixel size.')
            if name == 'viewBox' and not re.fullmatch(r'[\d.\-]+(?:\s+[\d.\-]+){3}', raw_value.strip()):
                raise ValueError('SVG viewBox must contain four numbers.')
            cleaned.set(name, raw_value)
        if is_root:
            cleaned.set('role', 'img')
            if not cleaned.get('aria-label'):
                cleaned.set('aria-label', 'Question illustration')
        cleaned.text = element.text
        cleaned.tail = element.tail
        for child in element:
            cleaned.append(clean_element(child))
        return cleaned

    safe_root = clean_element(root, is_root=True)
    ET.register_namespace('', SVG_NS)
    return ET.tostring(safe_root, encoding='unicode', method='xml')
