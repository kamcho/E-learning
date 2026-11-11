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
    """Stop chat models from wasting a turn on “Ready, paste your text”."""
    return [
        '## How to respond',
        '',
        '- If this message already includes KICD curriculum or outcomes text (below the divider '
        'or in the same user message), reply with ONLY the JSON object — no introduction.',
        '- Do NOT say “Ready”, “Please paste”, ask questions, or wait for confirmation.',
        '- If there is NO KICD source text in the message yet, reply with exactly one line: '
        'NO_KICD_TEXT_YET (and nothing else).',
        '- Match strand_name and sub_strand_name exactly to the Soma Smart list when one is provided.',
    ]
