"""Plain-text cleanup for AI tutor output shown without a markdown renderer."""

import re


def sanitize_tutor_plaintext(text: str) -> str:
    """Remove common markdown markers while keeping LaTeX $...$ intact."""
    if not text:
        return text
    cleaned = text
    cleaned = re.sub(r'\*\*(.+?)\*\*', r'\1', cleaned)
    cleaned = re.sub(r'__(.+?)__', r'\1', cleaned)
    cleaned = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', cleaned)
    cleaned = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'\1', cleaned)
    cleaned = re.sub(r'^\s*#{1,6}\s+', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
    return cleaned.strip()