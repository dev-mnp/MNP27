from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_item_comes_here_flag"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("session_name", models.CharField(max_length=120, unique=True)),
                ("event_year", models.PositiveIntegerField(default=django.utils.timezone.localdate().year)),
                ("is_active", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "Event Session",
                "verbose_name_plural": "Event Sessions",
                "db_table": "event_sessions",
                "ordering": ["-is_active", "-event_year", "session_name"],
            },
        ),
        migrations.CreateModel(
            name="SeatAllocationRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_file_name", models.CharField(blank=True, max_length=255, null=True)),
                ("application_number", models.CharField(blank=True, max_length=120, null=True)),
                ("beneficiary_name", models.CharField(blank=True, max_length=255, null=True)),
                ("district", models.CharField(blank=True, max_length=255, null=True)),
                ("requested_item", models.CharField(max_length=255)),
                ("quantity", models.PositiveIntegerField(default=0)),
                ("waiting_hall_quantity", models.PositiveIntegerField(default=0)),
                ("token_quantity", models.PositiveIntegerField(default=0)),
                ("beneficiary_type", models.CharField(blank=True, max_length=30, null=True)),
                ("item_type", models.CharField(blank=True, max_length=30, null=True)),
                ("comments", models.TextField(blank=True, null=True)),
                ("master_row", models.JSONField(blank=True, default=dict)),
                ("master_headers", models.JSONField(blank=True, default=list)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("sequence_no", models.PositiveIntegerField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_seat_allocation_rows", to="core.appuser")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="seat_allocation_rows", to="core.eventsession")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_seat_allocation_rows", to="core.appuser")),
            ],
            options={
                "verbose_name": "Seat Allocation Row",
                "verbose_name_plural": "Seat Allocation Rows",
                "db_table": "seat_allocation_rows",
                "ordering": ["session", "sort_order", "district", "requested_item", "application_number", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="eventsession",
            index=models.Index(fields=["is_active"], name="event_sessi_is_acti_8893e8_idx"),
        ),
        migrations.AddIndex(
            model_name="eventsession",
            index=models.Index(fields=["event_year"], name="event_sessi_event_y_3e85ab_idx"),
        ),
        migrations.AddIndex(
            model_name="seatallocationrow",
            index=models.Index(fields=["session", "sort_order"], name="seat_alloca_session_6db258_idx"),
        ),
        migrations.AddIndex(
            model_name="seatallocationrow",
            index=models.Index(fields=["session", "beneficiary_type"], name="seat_alloca_session_4e4bb9_idx"),
        ),
        migrations.AddIndex(
            model_name="seatallocationrow",
            index=models.Index(fields=["session", "requested_item"], name="seat_alloca_session_501333_idx"),
        ),
        migrations.AddIndex(
            model_name="seatallocationrow",
            index=models.Index(fields=["session", "sequence_no"], name="seat_alloca_session_0f122a_idx"),
        ),
    ]
