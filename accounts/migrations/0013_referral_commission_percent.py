from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def rate_to_percent(apps, schema_editor):
    MyUser = apps.get_model('accounts', 'MyUser')
    for user in MyUser.objects.exclude(referral_commission_rate__isnull=True):
        percent = (Decimal(str(user.referral_commission_rate)) * Decimal('100')).quantize(
            Decimal('0.01'),
        )
        MyUser.objects.filter(pk=user.pk).update(referral_commission_percent=percent)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_myuser_referral_commission_rate'),
    ]

    operations = [
        migrations.AddField(
            model_name='myuser',
            name='referral_commission_percent',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Commission percentage (0–75). Empty uses platform default.',
                max_digits=5,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0')),
                    django.core.validators.MaxValueValidator(Decimal('75')),
                ],
            ),
        ),
        migrations.RunPython(rate_to_percent, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='myuser',
            name='referral_commission_rate',
        ),
    ]