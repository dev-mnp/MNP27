from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_phase2_schema_sync"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventsession",
            name="phase2_grouped_quantity_total",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="eventsession",
            name="phase2_grouped_row_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="eventsession",
            name="phase2_source_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="eventsession",
            name="phase2_source_quantity_total",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="eventsession",
            name="phase2_source_row_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
