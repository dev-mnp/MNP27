from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_aid_name_of_beneficiary"),
    ]

    operations = [
        migrations.AddField(
            model_name="districtbeneficiaryentry",
            name="item_comes_here",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="publicbeneficiaryentry",
            name="item_comes_here",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="institutionsbeneficiaryentry",
            name="item_comes_here",
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
