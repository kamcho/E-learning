import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_alter_student_middle_name'),
        ('subscriptions', '0002_subscription_tests_remaining_subscription_tests_used_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionplan',
            name='grade_band',
            field=models.CharField(
                blank=True,
                choices=[
                    ('play-group-grade-3', 'Play Group–Grade 3'),
                    ('grade-4-6', 'Grades 4–6'),
                    ('grade-7-12', 'Grades 7–12'),
                ],
                default='',
                help_text='Grade band this per-exam plan applies to.',
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name='subscription',
            name='student',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='subscriptions',
                to='accounts.student',
            ),
        ),
        migrations.AddField(
            model_name='payment',
            name='student',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='subscription_payments',
                to='accounts.student',
            ),
        ),
    ]
