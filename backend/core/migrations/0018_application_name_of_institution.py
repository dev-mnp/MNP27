from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_usermodulepermission_can_reopen"),
    ]

    operations = [
        migrations.AddField(
            model_name="districtbeneficiaryentry",
            name="name_of_institution",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="institutionsbeneficiaryentry",
            name="name_of_institution",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="publicbeneficiaryentry",
            name="name_of_institution",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
