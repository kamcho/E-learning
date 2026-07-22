from django.conf import settings

from .exceptions import AIConfigurationError, AITaskError


class OpenAIClient:
    """Thin wrapper around the OpenAI chat completions API."""

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key if api_key is not None else getattr(settings, 'OPENAI_API_KEY', '')
        self.model = model or getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')

    def is_configured(self):
        return bool(self.api_key)

    def chat(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
        if not self.is_configured():
            raise AIConfigurationError(
                'OpenAI is not configured. Set the OPENAI_API_KEY environment variable.'
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIConfigurationError(
                'The openai package is not installed. Run: pip install openai'
            ) from exc

        client = OpenAI(api_key=self.api_key)
        try:
            response = client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
            )
        except Exception as exc:
            raise AITaskError(f'OpenAI request failed: {exc}') from exc

        content = response.choices[0].message.content
        if not content or not content.strip():
            raise AITaskError('OpenAI returned an empty response.')
        return content.strip()
