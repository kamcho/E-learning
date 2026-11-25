"""Public landing-page AI assistant — answers questions about Soma Smart."""

from __future__ import annotations

import hashlib
import json
import logging

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from accounts.auth_utils import get_client_ip
from core.ai.client import OpenAIClient
from core.ai.exceptions import AIConfigurationError, AITaskError
from subscriptions.models import SubscriptionPlan

logger = logging.getLogger(__name__)

SESSION_KEY = 'landing_assistant_history'
THREAD_SESSION_KEY = 'landing_assistant_thread_uuid'
MAX_HISTORY_MESSAGES = 20
MAX_MESSAGE_CHARS = 2000

SYSTEM_PROMPT = """You are the Soma Smart website assistant — warm, clear, and accurate.

Soma Smart (somasmartassesments.com) is a Kenya CBC e-learning platform for learners PP1 through Grade 9.
It offers KPSEA, KJSEA, and KCBE-style practice exams, curriculum-aligned notes, progress tracking for parents,
teacher class codes, school bundles, and AI tutor explanations when a learner misses a question.

Rules:
- Answer only about Soma Smart, CBC learning, exams on this platform, subscriptions, signing up, and how to use the site.
- Use the JSON facts in each user message for current plan prices and URLs — do not invent prices or features.
- Plain text only: no markdown, no asterisks, no hashtags. Short paragraphs; bullets with "•" if needed.
- Encourage a free practice exam (no signup) when someone wants to try the product.
- For account-specific billing or "my child's progress", say they should sign in to their dashboard or contact WhatsApp support.
- Never claim KICD official endorsement unless the user asks; say content is aligned to CBC strands/objectives.
- Keep replies under 900 characters unless the user asks for detail.
- Reply in the user's language when they write in Swahili; otherwise use English.
"""


def _trim_history(history):
    if not history:
        return []
    cleaned = []
    for row in history[-MAX_HISTORY_MESSAGES:]:
        role = (row.get('role') or '').strip()
        content = (row.get('content') or '').strip()
        if role in ('user', 'assistant') and content:
            cleaned.append({'role': role, 'content': content[:MAX_MESSAGE_CHARS]})
    return cleaned


def get_session_history(request):
    raw = request.session.get(SESSION_KEY) or []
    return _trim_history(raw)


def save_session_history(request, history):
    request.session[SESSION_KEY] = _trim_history(history)
    request.session.modified = True


def clear_session_history(request):
    if SESSION_KEY in request.session:
        del request.session[SESSION_KEY]
        request.session.modified = True


def build_facts_payload(request) -> dict:
    plans = list(
        SubscriptionPlan.objects.filter(is_active=True)
        .order_by('sort_order', 'price_kes')
        .values('name', 'price_kes', 'plan_type', 'grade_band', 'duration_days', 'max_tests')[:16]
    )
    user_line = None
    if request.user.is_authenticated:
        user = request.user
        user_line = {
            'signed_in': True,
            'role': getattr(user, 'role', ''),
            'display_name': user.get_full_name() or str(user),
            'dashboard_hint': 'Use the dashboard after sign-in for progress and subscriptions.',
        }
    else:
        user_line = {'signed_in': False}

    return {
        'product': 'Soma Smart — CBC learning and exam practice for PP1–Grade 9 in Kenya.',
        'exams': 'Practice for KPSEA, KJSEA, and KCBE-style assessments.',
        'free_practice_exam_url': request.build_absolute_uri(reverse('core:exam_wizard')),
        'exams_list_url': request.build_absolute_uri(reverse('core:exams_list')),
        'signup_url': request.build_absolute_uri(reverse('accounts:signup')),
        'signin_url': request.build_absolute_uri(reverse('accounts:signin')),
        'subscription_plans_url': request.build_absolute_uri(reverse('subscriptions:plans')),
        'roles': {
            'guardian': 'Parents register learners and manage subscriptions.',
            'teacher': 'Teachers get a free class code and track learners.',
            'partner': 'Schools buy learner places and onboard teachers.',
        },
        'features': [
            'Interactive practice exams by grade and subject',
            'AI tutor explanations after wrong answers (during exams)',
            'Notes and revision aligned to CBC strands',
            'Parent progress tracking',
            'Weekly, monthly, and per-exam payment options',
        ],
        'plans': plans,
        'visitor': user_line,
        'support_whatsapp': (getattr(settings, 'WHATSAPP_DISPLAY_NUMBER', '') or '').strip(),
    }


def assistant_is_enabled():
    return bool(getattr(settings, 'OPENAI_API_KEY', ''))


def _hash_client_ip(request) -> str:
    raw = (get_client_ip(request) or 'unknown').encode('utf-8', errors='replace')
    return hashlib.sha256(raw).hexdigest()


def ensure_assistant_thread(request):
    """Get or create a durable chat thread for this browser session / visitor."""
    from core.models import LandingAssistantThread

    if not request.session.session_key:
        request.session.create()

    thread_uuid = request.session.get(THREAD_SESSION_KEY)
    if thread_uuid:
        thread = LandingAssistantThread.objects.filter(uuid=thread_uuid).first()
        if thread:
            _maybe_attach_user_to_thread(thread, request)
            return thread

    thread = LandingAssistantThread.objects.create(
        django_session_key=request.session.session_key or '',
        user=request.user if getattr(request.user, 'is_authenticated', False) else None,
        ip_hash=_hash_client_ip(request),
        user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:512],
    )
    request.session[THREAD_SESSION_KEY] = str(thread.uuid)
    request.session.modified = True
    return thread


def _maybe_attach_user_to_thread(thread, request):
    if not getattr(request.user, 'is_authenticated', False):
        return
    if thread.user_id == request.user.pk:
        return
    thread.user = request.user
    thread.save(update_fields=['user', 'updated_at'])


def record_assistant_exchange(thread, user_message: str, assistant_message: str, *, ai_enabled: bool):
    """Persist one user question and assistant reply."""
    from core.models import LandingAssistantMessage, LandingAssistantThread

    user_text = (user_message or '').strip()[:MAX_MESSAGE_CHARS]
    assistant_text = (assistant_message or '').strip()[:MAX_MESSAGE_CHARS]
    if not user_text:
        return

    LandingAssistantMessage.objects.create(
        thread=thread,
        role=LandingAssistantMessage.Role.USER,
        content=user_text,
    )
    LandingAssistantMessage.objects.create(
        thread=thread,
        role=LandingAssistantMessage.Role.ASSISTANT,
        content=assistant_text,
        ai_enabled=ai_enabled,
    )
    LandingAssistantThread.objects.filter(pk=thread.pk).update(updated_at=timezone.now())


def generate_landing_assistant_reply(request, user_message: str) -> str:
    """Append user message to session history and return assistant reply."""
    text = (user_message or '').strip()
    if not text:
        raise ValueError('Message is required.')
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[:MAX_MESSAGE_CHARS]

    history = get_session_history(request)
    facts = build_facts_payload(request)
    user_payload = json.dumps(
        {'facts': facts, 'question': text},
        ensure_ascii=False,
        default=str,
    )

    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    for row in history:
        messages.append({'role': row['role'], 'content': row['content']})
    messages.append({'role': 'user', 'content': user_payload})

    client = OpenAIClient(
        model=getattr(settings, 'LANDING_ASSISTANT_MODEL', '') or None,
        timeout=float(getattr(settings, 'LANDING_ASSISTANT_TIMEOUT', 25)),
        max_tokens=int(getattr(settings, 'LANDING_ASSISTANT_MAX_TOKENS', 550)),
    )
    client.max_retries = 0

    try:
        reply = client.chat_conversation(messages=messages, temperature=0.35)
    except AIConfigurationError:
        raise
    except AITaskError as exc:
        logger.warning('Landing assistant AI error: %s', exc)
        raise

    history.append({'role': 'user', 'content': text})
    history.append({'role': 'assistant', 'content': reply})
    save_session_history(request, history)
    return reply


def fallback_reply_no_ai() -> str:
    return (
        'The AI assistant is not configured on this server. '
        'You can try a free practice exam from the landing page, browse pricing, or contact us via WhatsApp.'
    )