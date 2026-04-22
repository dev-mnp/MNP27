from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from core import models
from core.application_entry import attachment_service


class AttachmentServiceTests(TestCase):
    def setUp(self):
        self.user = models.AppUser.objects.create_superuser(
            email="admin@example.com",
            password="testpass123",
            role=models.RoleChoices.ADMIN,
            status=models.StatusChoices.ACTIVE,
        )
        self.district = models.DistrictMaster.objects.create(
            district_name="Ariyalur",
            allotted_budget="100000.00",
            president_name="District President",
            mobile_number="9876543210",
            application_number="D001",
            is_active=True,
        )
        self.article = models.Article.objects.create(
            article_name="Wheelchair",
            article_name_tk="Wheel Token",
            cost_per_unit="5000.00",
            item_type=models.ItemTypeChoices.ARTICLE,
            category="Mobility",
            master_category="Medical",
            combo=False,
            is_active=True,
        )

    def test_prefixed_attachment_name_preserves_prefix_and_extension(self):
        name = attachment_service.prefixed_attachment_name("D001", "income.pdf", "")
        self.assertEqual(name, "D001_income.pdf")

    def test_save_temp_attachment_upload_registers_temp_row(self):
        request = SimpleNamespace(
            POST={"file_name": "receipt"},
            FILES={
                "file": BytesIO(b"demo"),
            },
            user=self.user,
        )
        uploaded = request.FILES["file"]
        uploaded.name = "receipt.pdf"
        uploaded.size = 4
        uploaded.content_type = "application/pdf"

        class FakeSession(dict):
            modified = False

        request.session = FakeSession()

        with patch("core.application_entry.attachment_service.drive_service.is_configured", return_value=True), patch(
            "core.application_entry.attachment_service.drive_service.upload_attachment",
            return_value=SimpleNamespace(file_id="file-1", mime_type="application/pdf", view_url="https://drive.google.com/file-1"),
        ):
            ok, message = attachment_service.save_temp_attachment_upload(
                request=request,
                application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
                form_token="token-1",
                initial_prefix=self.district.application_number,
                save_kwargs={"district": self.district},
                temp_scope_filters={"district": self.district},
            )

        self.assertTrue(ok)
        self.assertIn("uploaded", message.lower())
        attachment = models.ApplicationAttachment.objects.get(drive_file_id="file-1")
        self.assertEqual(attachment.status, models.ApplicationAttachmentStatusChoices.TEMP)
        self.assertEqual(attachment.draft_uid, "token-1")
        self.assertEqual(attachment.file_name, "D001_receipt.pdf")

    def test_manual_drive_sync_registers_prefixed_file(self):
        with patch(
            "core.application_entry.attachment_service.drive_service.google_drive.list_application_attachments",
            return_value=[
                {
                    "file_id": "drive-99",
                    "file_name": "D001_income.pdf",
                    "mime_type": "application/pdf",
                    "view_url": "https://drive.google.com/file-99",
                }
            ],
        ):
            attachments = attachment_service.sync_drive_attachments_for_application(
                application_type=models.ApplicationAttachmentTypeChoices.DISTRICT,
                application_reference="D001",
                district=self.district,
            )

        self.assertEqual(len(attachments), 1)
        self.assertTrue(models.ApplicationAttachment.objects.filter(drive_file_id="drive-99").exists())
        registered = models.ApplicationAttachment.objects.get(drive_file_id="drive-99")
        self.assertEqual(registered.file_name, "D001_income.pdf")
        self.assertEqual(registered.prefix, "D001")
