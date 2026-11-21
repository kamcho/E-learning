from django.db import migrations, models


def rename_secondary_to_school(apps, schema_editor):
    GradeLevel = apps.get_model('subjects', 'GradeLevel')
    GradeLevel.objects.filter(level='Junior Secondary').update(level='Junior School')
    GradeLevel.objects.filter(level='Senior Secondary').update(level='Senior School')


def rename_school_to_secondary(apps, schema_editor):
    GradeLevel = apps.get_model('subjects', 'GradeLevel')
    GradeLevel.objects.filter(level='Junior School').update(level='Junior Secondary')
    GradeLevel.objects.filter(level='Senior School').update(level='Senior Secondary')


class Migration(migrations.Migration):

    dependencies = [
        ('subjects', '0006_objective_name_lengths'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gradelevel',
            name='level',
            field=models.CharField(
                choices=[
                    ('ECDE', 'ECDE'),
                    ('Lower Primary', 'Lower Primary'),
                    ('Upper Primary', 'Upper Primary'),
                    ('Junior School', 'Junior School'),
                    ('Senior School', 'Senior School'),
                ],
                max_length=50,
            ),
        ),
        migrations.RunPython(rename_secondary_to_school, rename_school_to_secondary),
    ]