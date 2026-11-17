"""
Site visit tracking and crawler/bot detection utilities.
"""
import re
from datetime import timedelta
from django.utils import timezone

from accounts.auth_utils import get_client_ip

# Known crawlers, search engines, SEO bots, scrapers, and automated tools.
KNOWN_BOT_SIGNATURES = (
    # Search engines
    ('googlebot', 'Googlebot'),
    ('bingbot', 'Bingbot'),
    ('slurp', 'Yahoo Slurp'),
    ('duckduckbot', 'DuckDuckBot'),
    ('baiduspider', 'Baidu Spider'),
    ('yandexbot', 'YandexBot'),
    ('sogou', 'Sogou Spider'),
    ('exabot', 'Exabot'),
    ('facebot', 'Facebook Bot'),
    ('facebookexternalhit', 'Facebook External Hit'),
    ('ia_archiver', 'Alexa/Internet Archive'),
    ('twitterbot', 'Twitterbot'),
    ('linkedinbot', 'LinkedInBot'),
    ('whatsapp', 'WhatsApp Preview'),
    ('telegrambot', 'TelegramBot'),
    ('slackbot', 'Slackbot'),
    ('discordbot', 'Discordbot'),
    ('applebot', 'Applebot'),
    ('amazonbot', 'Amazonbot'),
    # SEO / Crawler / Monitoring tools
    ('ahrefsbot', 'AhrefsBot'),
    ('semrushbot', 'SEMrushBot'),
    ('semrush', 'SEMrush'),
    ('dotbot', 'DotBot'),
    ('mj12bot', 'Majestic-12'),
    ('rogerbot', 'Moz Rogerbot'),
    ('petalbot', 'PetalBot'),
    ('bytespider', 'ByteDance Spider'),
    ('screaming frog', 'Screaming Frog'),
    ('blexbot', 'BLEXBot'),
    ('seekport', 'Seekport Crawler'),
    ('serpstatbot', 'SerpstatBot'),
    ('dataforseo', 'DataForSEO'),
    ('uptimerobot', 'UptimeRobot'),
    ('pingdom', 'Pingdom'),
    ('freshping', 'Freshping'),
    ('site24x7', 'Site24x7'),
    ('statuscake', 'StatusCake'),
    # Automation & HTTP clients
    ('python-requests', 'Python Requests'),
    ('python-urllib', 'Python Urllib'),
    ('aiohttp', 'aiohttp'),
    ('httpx', 'HTTPX'),
    ('curl', 'cURL'),
    ('wget', 'Wget'),
    ('go-http-client', 'Go HTTP Client'),
    ('postman', 'Postman'),
    ('insomnia', 'Insomnia'),
    ('httpie', 'HTTPie'),
    ('headlesschrome', 'Headless Chrome'),
    ('phantomjs', 'PhantomJS'),
    ('puppeteer', 'Puppeteer'),
    ('playwright', 'Playwright'),
    ('selenium', 'Selenium'),
    ('scrapy', 'Scrapy'),
    # Security scanners
    ('censysinspect', 'Censys Scanner'),
    ('shodan', 'Shodan Scanner'),
    ('nmap', 'Nmap Scanner'),
    ('nikto', 'Nikto Scanner'),
    ('zgrab', 'ZGrab Scanner'),
    ('masscan', 'Masscan Scanner'),
)

GENERIC_BOT_TOKENS = (
    'bot',
    'crawl',
    'spider',
    'scrape',
    'archiver',
    'transcoder',
    'fetcher',
    'preview',
    'checker',
    'probe',
    'scanner',
)


def detect_crawler_or_bot(user_agent: str) -> tuple[bool, str]:
    """
    Returns (is_bot, bot_name).
    Identifies search engines, SEO bots, scrapers, and automated scripts.
    """
    if not user_agent or not user_agent.strip():
        return True, 'Missing User-Agent'

    ua_lower = user_agent.lower()

    for token, label in KNOWN_BOT_SIGNATURES:
        if token in ua_lower:
            return True, label

    for token in GENERIC_BOT_TOKENS:
        if token in ua_lower:
            return True, f'Bot ({token.capitalize()})'

    return False, ''


def parse_browser_os(user_agent: str) -> str:
    """
    Extract a concise, human-friendly summary like 'Chrome on Windows'
    or 'Safari on iPhone' from the user-agent string.
    """
    if not user_agent:
        return 'Unknown'

    ua = user_agent.lower()

    # Browser
    if 'edg/' in ua or 'edge/' in ua:
        browser = 'Edge'
    elif 'opr/' in ua or 'opera' in ua:
        browser = 'Opera'
    elif 'chrome/' in ua and 'chromium' not in ua:
        browser = 'Chrome'
    elif 'firefox/' in ua:
        browser = 'Firefox'
    elif 'safari/' in ua and 'chrome' not in ua:
        browser = 'Safari'
    else:
        browser = 'Browser'

    # OS / Device
    if 'windows' in ua:
        os = 'Windows'
    elif 'iphone' in ua:
        os = 'iPhone'
    elif 'ipad' in ua:
        os = 'iPad'
    elif 'android' in ua:
        os = 'Android'
    elif 'macintosh' in ua or 'mac os' in ua:
        os = 'macOS'
    elif 'linux' in ua:
        os = 'Linux'
    elif 'cros' in ua:
        os = 'ChromeOS'
    else:
        os = ''

    return f'{browser} on {os}' if os else browser


EXCLUDED_PATH_PREFIXES = (
    '/static/',
    '/media/',
    '/favicon.ico',
    '/robots.txt',
    '/sitemap.xml',
    '/apple-touch-icon',
    '/.well-known/',
    '/accounts/admin/site-visits/',
    '/accounts/admin/database-backup/',
)

STATIC_EXTENSIONS = (
    '.js', '.css', '.png', '.jpg', '.jpeg', '.gif',
    '.svg', '.ico', '.woff', '.woff2', '.ttf', '.map',
)


def record_site_visit(request, response):
    """
    Persist a site visit record.
    Safe against exceptions so user requests are never blocked or delayed.
    """
    try:
        path = getattr(request, 'path', '') or ''
        if not path:
            return

        if any(path.startswith(prefix) for prefix in EXCLUDED_PATH_PREFIXES):
            return

        if any(path.endswith(ext) for ext in STATIC_EXTENSIONS):
            return

        method = (getattr(request, 'method', 'GET') or 'GET').upper()
        if method not in ('GET', 'POST'):
            return

        user_agent = request.META.get('HTTP_USER_AGENT', '')
        is_bot, bot_name = detect_crawler_or_bot(user_agent)

        ip = get_client_ip(request)
        if ip == 'unknown':
            ip = None

        user = getattr(request, 'user', None)
        authenticated_user = user if (user and getattr(user, 'is_authenticated', False)) else None

        referrer = (request.META.get('HTTP_REFERER', '') or '')[:512]
        status_code = getattr(response, 'status_code', None)

        from accounts.models import SiteVisit

        SiteVisit.objects.create(
            ip_address=ip,
            path=path[:512],
            method=method[:10],
            user=authenticated_user,
            user_agent=user_agent,
            referrer=referrer,
            status_code=status_code,
            is_bot=is_bot,
            bot_name=(bot_name or '')[:64],
        )
    except Exception:
        # Never fail the user's request due to visit tracking
        pass
