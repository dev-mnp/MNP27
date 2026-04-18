from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0033_expand_mobile_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendor",
            name="phone_number",
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
    ]

