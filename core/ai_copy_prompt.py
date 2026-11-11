"""Shared instructions for copy-paste prompts sent to external AI tools."""


def paste_safe_json_delivery_rules():
    """Lines appended so models return JSON that is easy to reuse."""
    return [
        '## Critical — raw JSON only',
        '',
        'Return ONE JSON object. Do not include explanations before or after.',
        '',
        'Character rules:',
        '- Use ONLY straight ASCII double quotes (") for keys and string values.',
        '- NEVER use curly/smart quotes (“ ” ‘ ’).',
        '',
        'Formatting rules:',
        '- Do NOT wrap JSON in markdown code fences (no ```json).',
        '- Do NOT add backslashes before brackets or braces (no \\[, no \\{).',
        '- Pretty-printed JSON with normal newlines is fine.',
    ]
