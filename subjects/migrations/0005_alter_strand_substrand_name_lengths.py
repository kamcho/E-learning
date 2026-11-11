from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subjects', '0004_teachersubject'),
    ]

    operations = [
        migrations.AlterField(
            model_name='strand',
            name='name',
            field=models.CharField(max_length=150),
        ),
        migrations.AlterField(
            model_name='strand',
            name='slug',
            field=models.SlugField(max_length=80, unique=True),
        ),
        migrations.AlterField(
            model_name='substrand',
            name='name',
            field=models.CharField(max_length=500),
        ),
        migrations.AlterField(
            model_name='substrand',
            name='slug',
            field=models.SlugField(max_length=80, unique=True),
        ),
    ]
