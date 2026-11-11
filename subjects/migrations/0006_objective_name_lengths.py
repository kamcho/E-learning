from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subjects', '0005_alter_strand_substrand_name_lengths'),
    ]

    operations = [
        migrations.AlterField(
            model_name='strandobjective',
            name='name',
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name='substrandobjective',
            name='name',
            field=models.CharField(max_length=255),
        ),
    ]
