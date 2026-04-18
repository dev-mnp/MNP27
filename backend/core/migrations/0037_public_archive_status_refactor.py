from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_publicbeneficiaryentry_archive_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="publicbeneficiaryentry",
            name="archived_previous_status",
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.RunSQL(
            sql="""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'public_beneficiary_entries'
          AND column_name = 'is_archived'
    ) THEN
        UPDATE public_beneficiary_entries
        SET archived_previous_status = COALESCE(NULLIF(status, ''), 'draft'),
            status = 'archived'
        WHERE is_archived = TRUE
          AND status <> 'archived';
    END IF;
END$$;
""",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP INDEX IF EXISTS public_bene_is_archi_24f2df_idx;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="ALTER TABLE public_beneficiary_entries DROP COLUMN IF EXISTS is_archived;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
