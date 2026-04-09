from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0026_eventsession_phase2_reconciliation_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventsession",
            name="phase2_reconciliation_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
