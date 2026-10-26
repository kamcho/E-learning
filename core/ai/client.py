from django.conf import settings

from .exceptions import AIConfigurationError, AITaskError


class OpenAIClient:
    """Thin wrapper around the OpenAI chat completions API."""

    def __init__(self, api_key=None, model=None, timeout=None, max_tokens=None):
        self.api_key = api_key if api_key is not None else getattr(settings, 'OPENAI_API_KEY', '')
        self.model = model or getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
        self.timeout = timeout if timeout is not None else float(
            getattr(settings, 'OPENAI_TIMEOUT', 60)
        )
        self.max_tokens = max_tokens if max_tokens is not None else int(
            getattr(settings, 'OPENAI_MAX_TOKENS', 300)
        )
        self.max_retries = int(getattr(settings, 'OPENAI_MAX_RETRIES', 1))

    def is_configured(self):
        return bool(self.api_key)

    def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        json_mode: bool = False,
    ) -> str:
        if not self.is_configured():
            raise AIConfigurationError(
                'OpenAI is not configured. Set the OPENAI_API_KEY environment variable.'
            )

        try:
            from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError
        except ImportError as exc:
            raise AIConfigurationError(
                'The openai package is not installed. Run: pip install openai'
            ) from exc

        client = OpenAI(api_key=self.api_key, timeout=self.timeout)
        last_exc = None
        attempts = max(1, self.max_retries + 1)

        for attempt in range(attempts):
            try:
                request = {
                    'model': self.model,
                    'temperature': temperature,
                    'max_tokens': self.max_tokens,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt},
                    ],
                }
                if json_mode:
                    request['response_format'] = {'type': 'json_object'}
                response = client.chat.completions.create(**request)
                content = response.choices[0].message.content
                if not content or not content.strip():
                    raise AITaskError('OpenAI returned an empty response.')
                return content.strip()
            except AITaskError:
                raise
            except APITimeoutError as exc:
                last_exc = exc
                if attempt + 1 >= attempts:
                    raise AITaskError(
                        'The AI tutor took too long to respond. Please try again.'
                    ) from exc
            except APIConnectionError as exc:
                last_exc = exc
                if attempt + 1 >= attempts:
                    raise AITaskError(
                        'Could not reach the AI tutor. Check your internet connection and try again.'
                    ) from exc
            except RateLimitError as exc:
                raise AITaskError(
                    'The AI tutor is busy right now. Please wait a moment and try again.'
                ) from exc
            except Exception as exc:
                raise AITaskError(self._friendly_error(exc)) from exc

        raise AITaskError(self._friendly_error(last_exc or Exception('Unknown AI error')))

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        message = str(exc or '').strip()
        lowered = message.lower()
        if 'timed out' in lowered or 'timeout' in lowered:
            return 'The AI tutor took too long to respond. Please try again.'
        if 'connection' in lowered:
            return 'Could not reach the AI tutor. Check your internet connection and try again.'
        if message:
            return f'AI tutor unavailable: {message}'
        return 'AI tutor unavailable. Please try again.'
