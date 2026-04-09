from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_phase2_event_and_seat_allocation"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="eventsession",
            new_name="event_sessi_is_acti_ea8fbc_idx",
            old_name="event_sessi_is_acti_8893e8_idx",
        ),
        migrations.RenameIndex(
            model_name="eventsession",
            new_name="event_sessi_event_y_2e0fa6_idx",
            old_name="event_sessi_event_y_3e85ab_idx",
        ),
        migrations.RenameIndex(
            model_name="purchaseorder",
            new_name="purchase_or_purchas_49b03b_idx",
            old_name="purchase_or_purchas_b53c86_idx",
        ),
        migrations.RenameIndex(
            model_name="purchaseorder",
            new_name="purchase_or_status_86ae3f_idx",
            old_name="purchase_or_status_9d2e52_idx",
        ),
        migrations.RenameIndex(
            model_name="purchaseorder",
            new_name="purchase_or_created_a0c5eb_idx",
            old_name="purchase_or_created_5dd8ad_idx",
        ),
        migrations.RenameIndex(
            model_name="purchaseorderitem",
            new_name="purchase_or_purchas_a61376_idx",
            old_name="purchase_or_purchase_a0b903_idx",
        ),
        migrations.RenameIndex(
            model_name="purchaseorderitem",
            new_name="purchase_or_article_59dca9_idx",
            old_name="purchase_or_article_0a6707_idx",
        ),
        migrations.RenameIndex(
            model_name="seatallocationrow",
            new_name="seat_alloca_session_a45f13_idx",
            old_name="seat_alloca_session_6db258_idx",
        ),
        migrations.RenameIndex(
            model_name="seatallocationrow",
            new_name="seat_alloca_session_d477f8_idx",
            old_name="seat_alloca_session_4e4bb9_idx",
        ),
        migrations.RenameIndex(
            model_name="seatallocationrow",
            new_name="seat_alloca_session_2f4f36_idx",
            old_name="seat_alloca_session_501333_idx",
        ),
        migrations.RenameIndex(
            model_name="seatallocationrow",
            new_name="seat_alloca_session_b6ac3b_idx",
            old_name="seat_alloca_session_0f122a_idx",
        ),
        migrations.AlterField(
            model_name="purchaseorder",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name="purchaseorderitem",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name="usermodulepermission",
            name="module_key",
            field=models.CharField(
                choices=[
                    ("application_entry", "Application Entry"),
                    ("article_management", "Article Management"),
                    ("base_files", "Base Files"),
                    ("inventory_planning", "Inventory Planning"),
                    ("seat_allocation", "Seat Allocation"),
                    ("sequence_list", "Sequence List"),
                    ("order_fund_request", "Order & Fund Request"),
                    ("purchase_order", "Purchase Order"),
                    ("audit_logs", "Audit Logs"),
                    ("user_management", "User Management"),
                ],
                max_length=64,
            ),
        ),
    ]
