from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from subscriptions.mpesa import MpesaAPIError, MpesaConfigError
from subscriptions.mpesa_pull import register_pull_transactions


class Command(BaseCommand):
    help = 'Register the pay bill shortcode for Daraja Pull Transactions (one-time per shortcode).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--nominated-number',
            dest='nominated_number',
            default='',
            help='2547… MSISDN on pay bill KYC (defaults to MPESA_PULL_NOMINATED_NUMBER).',
        )

    def handle(self, *args, **options):
        nominated = options['nominated_number'] or settings.MPESA_PULL_NOMINATED_NUMBER
        if not nominated:
            raise CommandError(
                'Set MPESA_PULL_NOMINATED_NUMBER in .env or pass --nominated-number=2547…',
            )
        try:
            data = register_pull_transactions(nominated_number=nominated)
        except (MpesaConfigError, MpesaAPIError) as exc:
            raise CommandError(str(exc)) from exc

        code = str(
            data.get('ResponseStatus')
            or data.get('ResponseCode')
            or data.get('responseCode')
            or '',
        )
        message = (
            data.get('ResponseDescription')
            or data.get('responseMessage')
            or data
        )
        style = self.style.SUCCESS if code in ('1000', '1001') else self.style.WARNING
        self.stdout.write(style(f'Pull register response ({code}): {message}'))