from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_alter_publicbeneficiaryentry_is_handicapped_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="fundrequestrecipient",
            constraint=models.UniqueConstraint(
                condition=models.Q(source_entry_id__isnull=False),
                fields=("beneficiary_type", "source_entry_id"),
                name="uniq_fund_request_recipient_source_global",
            ),
        ),
    ]
