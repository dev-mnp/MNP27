from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_purchaseorder_comments"),
    ]

    operations = [
        migrations.AddField(
            model_name="districtbeneficiaryentry",
            name="aadhar_number",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="institutionsbeneficiaryentry",
            name="aadhar_number",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
