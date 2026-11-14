from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_question_created_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='question',
            name='explanation_audio',
            field=models.FileField(
                blank=True,
                help_text='Optional pre-recorded explanation (used instead of TTS when present).',
                null=True,
                upload_to='questions/explanations/%Y/%m/',
            ),
        ),
        migrations.AddField(
            model_name='option',
            name='option_audio',
            field=models.FileField(
                blank=True,
                help_text='Optional audio for this answer choice.',
                null=True,
                upload_to='questions/options/audio/%Y/%m/',
            ),
        ),
    ]