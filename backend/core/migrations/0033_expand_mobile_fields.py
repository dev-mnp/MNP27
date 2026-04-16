from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0032_applicationattachment_google_drive_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="districtmaster",
            name="mobile_number",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="institutionsbeneficiaryentry",
            name="mobile",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name="publicbeneficiaryentry",
            name="mobile",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name="publicbeneficiaryhistory",
            name="mobile",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]

