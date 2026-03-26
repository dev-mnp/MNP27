from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_application_aadhaar_for_aid_rows"),
    ]

    operations = [
        migrations.AddField(
            model_name="districtbeneficiaryentry",
            name="name_of_beneficiary",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="institutionsbeneficiaryentry",
            name="name_of_beneficiary",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
