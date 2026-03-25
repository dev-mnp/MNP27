from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_rename_fundreq_article_vendor_idx_fund_reques_vendor__1e094a_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="usermodulepermission",
            name="can_reopen",
            field=models.BooleanField(default=False),
        ),
    ]
