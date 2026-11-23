from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


def backfill_commission_kes(apps, schema_editor):
    ReferralPointLog = apps.get_model('accounts', 'ReferralPointLog')
    rate = Decimal('0.10')
    for log in ReferralPointLog.objects.select_related('payment').iterator():
        if log.commission_kes and log.commission_kes > 0:
            continue
        payment = log.payment
        if not payment:
            continue
        amount = Decimal(str(payment.amount_kes))
        commission = (amount * rate).quantize(Decimal('0.01'))
        ReferralPointLog.objects.filter(pk=log.pk).update(commission_kes=commission)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_sitevisit'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='referralpointlog',
            name='commission_kes',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='KES commission earned from this referred subscription payment.',
                max_digits=10,
            ),
        ),
        migrations.CreateModel(
            name='ReferralPayout',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_kes', models.DecimalField(
                    decimal_places=2,
                    max_digits=10,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
                )),
                ('mpesa_receipt_number', models.CharField(blank=True, max_length=32)),
                ('note', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('recorded_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='referral_payouts_recorded',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('referrer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='referral_payouts',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ('-created_at',),
            },
        ),
        migrations.RunPython(backfill_commission_kes, migrations.RunPython.noop),
    ]