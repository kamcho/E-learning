from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_referral_commission_payouts'),
    ]

    operations = [
        migrations.AddField(
            model_name='myuser',
            name='referral_commission_rate',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Partner/referral commission rate (0–1). Empty uses platform default.',
                max_digits=5,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0')),
                    django.core.validators.MaxValueValidator(Decimal('1')),
                ],
            ),
        ),
    ]