from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0048_rename_others_bene_applica_9b1842_idx_others_bene_applica_c25bca_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="usermodulepermission",
            name="can_view_page_2",
            field=models.BooleanField(default=False),
        ),
    ]

