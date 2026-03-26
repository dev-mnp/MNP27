from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_purchase_order_module"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorder",
            name="comments",
            field=models.TextField(blank=True, null=True),
        ),
    ]
