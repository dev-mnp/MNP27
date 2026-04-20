from django.core.validators import MinLengthValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0038_alter_districtbeneficiaryentry_status_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="publicbeneficiaryentry",
            name="aadhar_number",
            field=models.CharField(
                blank=True,
                max_length=20,
                null=True,
                validators=[MinLengthValidator(12)],
            ),
        ),
        migrations.AddField(
            model_name="publicbeneficiaryentry",
            name="aadhaar_status",
            field=models.CharField(
                choices=[
                    ("VERIFIED", "Verified"),
                    ("NOT_AVAILABLE", "Not Available"),
                    ("PENDING_VERIFICATION", "Pending Verification"),
                ],
                default="PENDING_VERIFICATION",
                max_length=24,
            ),
        ),
        migrations.AddIndex(
            model_name="publicbeneficiaryentry",
            index=models.Index(fields=["aadhaar_status"], name="public_bene_aadhaar_a8a4ca_idx"),
        ),
    ]

