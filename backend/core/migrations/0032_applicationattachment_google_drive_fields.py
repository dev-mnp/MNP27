from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0031_labels_module"),
    ]

    operations = [
        migrations.AlterField(
            model_name="applicationattachment",
            name="file",
            field=models.FileField(blank=True, upload_to="application_attachments/%Y/%m/%d"),
        ),
        migrations.AddField(
            model_name="applicationattachment",
            name="drive_file_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="applicationattachment",
            name="drive_mime_type",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="applicationattachment",
            name="drive_view_url",
            field=models.URLField(blank=True),
        ),
    ]
