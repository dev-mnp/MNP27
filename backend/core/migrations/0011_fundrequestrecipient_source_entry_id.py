from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_districtbeneficiaryentry_cheque_rtgs_in_favour_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="fundrequestrecipient",
            name="source_entry_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
