from django.db import migrations, models
import django.db.models.deletion


def remove_attempts_without_learner(apps, schema_editor):
    UserAttempts = apps.get_model('core', 'UserAttempts')
    UserAttempts.objects.filter(student__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_student_linkedstudents'),
        ('core', '0006_userattempts_answers'),
    ]

    operations = [
        migrations.RunPython(remove_attempts_without_learner, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='userattempts',
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name='userattempts',
            name='student',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='attempts',
                to='accounts.student',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='userattempts',
            unique_together={('student', 'quiz')},
        ),
    ]
