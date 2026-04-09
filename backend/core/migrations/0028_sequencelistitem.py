from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0027_eventsession_phase2_reconciliation_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="SequenceListItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("item_name", models.CharField(max_length=255)),
                ("sequence_no", models.PositiveIntegerField()),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_sequence_list_items", to="core.appuser")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sequence_list_items", to="core.eventsession")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_sequence_list_items", to="core.appuser")),
            ],
            options={
                "verbose_name": "Sequence List Item",
                "verbose_name_plural": "Sequence List Items",
                "db_table": "sequence_list_items",
                "ordering": ["session", "sequence_no", "sort_order", "item_name"],
            },
        ),
        migrations.AddIndex(
            model_name="sequencelistitem",
            index=models.Index(fields=["session", "sequence_no"], name="sequence_li_session_68ddc8_idx"),
        ),
        migrations.AddIndex(
            model_name="sequencelistitem",
            index=models.Index(fields=["session", "sort_order"], name="sequence_li_session_8f80d2_idx"),
        ),
        migrations.AddConstraint(
            model_name="sequencelistitem",
            constraint=models.UniqueConstraint(fields=("session", "item_name"), name="uniq_sequence_item_per_session"),
        ),
        migrations.AddConstraint(
            model_name="sequencelistitem",
            constraint=models.UniqueConstraint(fields=("session", "sequence_no"), name="uniq_sequence_no_per_session"),
        ),
    ]
