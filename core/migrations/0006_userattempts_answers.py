from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_userattempts_student'),
    ]

    operations = [
        migrations.AddField(
            model_name='userattempts',
            name='answers',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
