from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_user_action_log'),
    ]

    operations = [
        migrations.AddField(
            model_name='myuser',
            name='totp_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Require an authenticator app code at sign-in.',
            ),
        ),
        migrations.AddField(
            model_name='myuser',
            name='totp_secret',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Encrypted TOTP shared secret (set via Security settings).',
                max_length=255,
            ),
        ),
    ]
