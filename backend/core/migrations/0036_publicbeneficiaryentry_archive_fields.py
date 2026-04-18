from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0035_rename_label_gener_session_sort_idx_label_gener_session_443b32_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="publicbeneficiaryentry",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="publicbeneficiaryentry",
            name="archived_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="archived_public_entries",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
