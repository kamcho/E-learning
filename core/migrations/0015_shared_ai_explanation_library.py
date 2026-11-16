import hashlib
import json

import django.db.models.deletion
from django.db import migrations, models


def consolidate_explanations(apps, schema_editor):
    Explanation = apps.get_model('core', 'AIExplanation')
    db_alias = schema_editor.connection.alias
    seen = set()
    rows = list(Explanation.objects.using(db_alias).order_by('created_at', 'uuid'))
    for row in rows:
        old_snapshot = row.prompt_snapshot or {}
        snapshot = {
            'question_id': str(row.question_id or ''),
            'question': old_snapshot.get('question', ''),
            'choices': old_snapshot.get('choices', []),
            'selected_answer': row.selected_answer or '',
            'grade_level': old_snapshot.get('grade_level', ''),
            'subject': old_snapshot.get('subject', ''),
        }
        serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        lookup_key = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
        if lookup_key in seen:
            row.delete(using=db_alias)
            continue
        row.lookup_key = lookup_key
        row.prompt_snapshot = snapshot
        row.save(using=db_alias, update_fields=['lookup_key', 'prompt_snapshot'])
        seen.add(lookup_key)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_aiexplanation'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='aiexplanation',
            name='core_aiexpl_attempt_q_idx',
        ),
        migrations.RemoveIndex(
            model_name='aiexplanation',
            name='core_aiexpl_demo_q_idx',
        ),
        migrations.RemoveField(model_name='aiexplanation', name='attempt'),
        migrations.RemoveField(model_name='aiexplanation', name='user'),
        migrations.RemoveField(model_name='aiexplanation', name='demo_id'),
        migrations.AddField(
            model_name='aiexplanation',
            name='lookup_key',
            field=models.CharField(blank=True, default='', max_length=64),
            preserve_default=False,
        ),
        migrations.RunPython(consolidate_explanations, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='aiexplanation',
            name='lookup_key',
            field=models.CharField(max_length=64, unique=True),
        ),
    ]
