from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_vendor_and_article_vendor_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="districtbeneficiaryentry",
            name="internal_notes",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="institutionsbeneficiaryentry",
            name="internal_notes",
            field=models.TextField(blank=True, null=True),
        ),
    ]
