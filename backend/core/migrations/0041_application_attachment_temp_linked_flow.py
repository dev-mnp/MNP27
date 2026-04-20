# Generated manually to safely support TEMP/LINKED application attachment workflow.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0040_rename_public_bene_aadhaar_a8a4ca_idx_public_bene_aadhaar_d37a07_idx"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE application_attachments "
                        "ADD COLUMN IF NOT EXISTS form_token varchar(64);"
                    ),
                    reverse_sql=(
                        "ALTER TABLE application_attachments "
                        "DROP COLUMN IF EXISTS form_token;"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE application_attachments "
                        "ADD COLUMN IF NOT EXISTS status varchar(20) "
                        "NOT NULL DEFAULT 'linked';"
                    ),
                    reverse_sql=(
                        "ALTER TABLE application_attachments "
                        "DROP COLUMN IF EXISTS status;"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE application_attachments "
                        "ADD COLUMN IF NOT EXISTS temp_expires_at timestamp with time zone;"
                    ),
                    reverse_sql=(
                        "ALTER TABLE application_attachments "
                        "DROP COLUMN IF EXISTS temp_expires_at;"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX IF NOT EXISTS application_attachments_status_idx "
                        "ON application_attachments (status);"
                    ),
                    reverse_sql=(
                        "DROP INDEX IF EXISTS application_attachments_status_idx;"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX IF NOT EXISTS application_attachments_form_token_idx "
                        "ON application_attachments (form_token);"
                    ),
                    reverse_sql=(
                        "DROP INDEX IF EXISTS application_attachments_form_token_idx;"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX IF NOT EXISTS application_attachments_temp_expires_at_idx "
                        "ON application_attachments (temp_expires_at);"
                    ),
                    reverse_sql=(
                        "DROP INDEX IF EXISTS application_attachments_temp_expires_at_idx;"
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="applicationattachment",
                    name="form_token",
                    field=models.CharField(blank=True, max_length=64, null=True),
                ),
                migrations.AddField(
                    model_name="applicationattachment",
                    name="status",
                    field=models.CharField(
                        choices=[("temp", "Temp"), ("linked", "Linked")],
                        default="linked",
                        max_length=20,
                    ),
                ),
                migrations.AddField(
                    model_name="applicationattachment",
                    name="temp_expires_at",
                    field=models.DateTimeField(blank=True, null=True),
                ),
                migrations.AddIndex(
                    model_name="applicationattachment",
                    index=models.Index(fields=["status"], name="application_attac_status_9f8eb0_idx"),
                ),
                migrations.AddIndex(
                    model_name="applicationattachment",
                    index=models.Index(fields=["form_token"], name="application_attac_form_to_6df95d_idx"),
                ),
                migrations.AddIndex(
                    model_name="applicationattachment",
                    index=models.Index(fields=["temp_expires_at"], name="application_attac_temp_ex_f95e2c_idx"),
                ),
            ],
        ),
    ]
