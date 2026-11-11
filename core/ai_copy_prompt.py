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


def external_ai_behavior_rules():
    """Two-turn or one-shot: JSON only once KICD source text is present."""
    return [
        '## How to respond',
        '',
        '- When the user message includes KICD curriculum or outcomes text (under ## KICD text '
        'or in a later message in this chat), reply with ONLY the JSON object — no introduction.',
        '- If the first message is only these instructions with no KICD body text yet, reply in '
        'one short sentence: ask them to paste the KICD document in their next message; '
        'then you will return only JSON.',
        '- Do not ask unrelated questions. Remember the subject and sub-strand list from the prompt.',
        '- Match strand_name and sub_strand_name exactly to the Soma Smart list when one is provided.',
    ]
