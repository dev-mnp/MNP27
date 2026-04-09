from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0028_sequencelistitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorder",
            name="gst_number",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
