from __future__ import annotations

import csv
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from core import models
from core.web_views import EXPORT_COLUMNS
from core.web_views import _phase2_master_change_state


class Phase2ModuleTests(TestCase):
    def setUp(self):
        self.user = models.AppUser.objects.create_superuser(
            email="admin@example.com",
            password="testpass123",
            role=models.RoleChoices.ADMIN,
            status=models.StatusChoices.ACTIVE,
        )
        self.client.force_login(self.user)

    def _public_master_row(self, *, application_number, name, requested_item, quantity, total_value, aadhar_number):
        row = {header: "" for header in EXPORT_COLUMNS}
        row.update(
            {
                "Application Number": application_number,
                "Beneficiary Name": name,
                "Requested Item": requested_item,
                "Quantity": str(quantity),
                "Cost Per Unit": "10000",
                "Total Value": str(total_value),
                "Address": "",
                "Mobile": "",
                "Aadhar Number": aadhar_number,
                "Name of Beneficiary": name,
                "Name of Institution": "",
                "Cheque / RTGS in Favour": "",
                "Handicapped Status": models.HandicappedStatusChoices.NO,
                "Gender": "",
                "Gender Category": "",
                "Beneficiary Type": "Public",
                "Item Type": "Aid",
                "Article Category": "",
                "Super Category Article": "",
                "Token Name": "",
                "Internal Notes": "",
                "Comments": "",
            }
        )
        return row

    def test_only_one_event_session_stays_active(self):
        first = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        second = models.EventSession.objects.create(session_name="2027 Event", event_year=2027, is_active=True)

        first.refresh_from_db()
        second.refresh_from_db()

        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)

    def test_user_guide_page_is_available_for_logged_in_user(self):
        response = self.client.get(reverse("ui:user-guide"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Guide")
        self.assertContains(response, "Application Entry")
        self.assertContains(response, "Seat Allocation")
        self.assertContains(response, "Token Generation")

    def test_seat_allocation_upload_keeps_same_master_row_key_as_separate_rows(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        csv_content = (
            "Application Number,Beneficiary Name,Requested Item,Quantity,Beneficiary Type,Item Type,Comments,Total Value\n"
            "D001,Ariyalur,Education Aid,1,District,Aid,E1,10000\n"
            "D001,Ariyalur,Education Aid,2,District,Aid,E1,20000\n"
        )
        uploaded = SimpleUploadedFile("master.csv", csv_content.encode("utf-8"), content_type="text/csv")

        response = self.client.post(
            reverse("ui:seat-allocation-list"),
            {"action": "upload_csv", "session": str(session.pk), "file": uploaded},
        )

        self.assertEqual(response.status_code, 302)
        rows = list(models.SeatAllocationRow.objects.filter(session=session))
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row.quantity for row in rows), 3)
        self.assertEqual(sum(row.token_quantity for row in rows), 3)

    def test_sequence_save_updates_all_matching_session_rows(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        article = models.Article.objects.create(
            article_name="Medical Aid",
            cost_per_unit=10000,
            item_type=models.ItemTypeChoices.AID,
            is_active=True,
        )
        models.PublicBeneficiaryEntry.objects.create(
            application_number="P001",
            name="Person 1",
            aadhar_number="123456789012",
            is_handicapped=models.HandicappedStatusChoices.NO,
            article=article,
            article_cost_per_unit=10000,
            quantity=1,
            total_amount=10000,
            status=models.BeneficiaryStatusChoices.SUBMITTED,
        )
        models.PublicBeneficiaryEntry.objects.create(
            application_number="P002",
            name="Person 2",
            aadhar_number="123456789013",
            is_handicapped=models.HandicappedStatusChoices.NO,
            article=article,
            article_cost_per_unit=10000,
            quantity=1,
            total_amount=10000,
            status=models.BeneficiaryStatusChoices.SUBMITTED,
        )
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="P001",
            beneficiary_name="Person 1",
            district="Non-District",
            requested_item="Medical Aid",
            quantity=1,
            token_quantity=1,
            beneficiary_type="Public",
            item_type="Aid",
            master_headers=EXPORT_COLUMNS,
            master_row=self._public_master_row(
                application_number="P001",
                name="Person 1",
                requested_item="Medical Aid",
                quantity=1,
                total_value=10000,
                aadhar_number="123456789012",
            ),
        )
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="P002",
            beneficiary_name="Person 2",
            district="Non-District",
            requested_item="Medical Aid",
            quantity=1,
            token_quantity=1,
            beneficiary_type="Public",
            item_type="Aid",
            master_headers=EXPORT_COLUMNS,
            master_row=self._public_master_row(
                application_number="P002",
                name="Person 2",
                requested_item="Medical Aid",
                quantity=1,
                total_value=10000,
                aadhar_number="123456789013",
            ),
        )

        response = self.client.post(
            reverse("ui:sequence-list"),
            {
                "action": "save_sequences",
                "session": str(session.pk),
                "item_name": ["Medical Aid"],
                "sequence_no": ["12"],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(models.SeatAllocationRow.objects.filter(session=session, sequence_no=12).count(), 2)
        submit_result = self.client.session.get("sequence_submit_result")
        self.assertIsNotNone(submit_result)
        labels = [check["label"] for check in submit_result["checks"]]
        self.assertIn("Final data integrity", labels)
        self.assertIn("Final Sequence vs Master Data", labels)
        self.assertIn("Final Sequence vs Seat Allocation", labels)
        self.assertTrue(submit_result["all_matched"])

    def test_sequence_save_persists_sequence_list_even_when_seat_allocation_is_out_of_sync(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        aid_article = models.Article.objects.create(
            article_name="Medical Aid",
            cost_per_unit=10000,
            item_type=models.ItemTypeChoices.AID,
            is_active=True,
        )
        extra_article = models.Article.objects.create(
            article_name="Hearing Aid",
            cost_per_unit=12000,
            item_type=models.ItemTypeChoices.AID,
            is_active=True,
        )
        models.PublicBeneficiaryEntry.objects.create(
            application_number="P001",
            name="Person 1",
            aadhar_number="123456789012",
            is_handicapped=models.HandicappedStatusChoices.NO,
            article=aid_article,
            article_cost_per_unit=10000,
            quantity=1,
            total_amount=10000,
            status=models.BeneficiaryStatusChoices.SUBMITTED,
        )
        models.PublicBeneficiaryEntry.objects.create(
            application_number="P002",
            name="Person 2",
            aadhar_number="123456789013",
            is_handicapped=models.HandicappedStatusChoices.NO,
            article=extra_article,
            article_cost_per_unit=12000,
            quantity=1,
            total_amount=12000,
            status=models.BeneficiaryStatusChoices.SUBMITTED,
        )
        seat_row = models.SeatAllocationRow.objects.create(
            session=session,
            application_number="P001",
            beneficiary_name="Person 1",
            district="Non-District",
            requested_item="Medical Aid",
            quantity=1,
            token_quantity=1,
            beneficiary_type="Public",
            item_type="Aid",
            master_headers=EXPORT_COLUMNS,
            master_row=self._public_master_row(
                application_number="P001",
                name="Person 1",
                requested_item="Medical Aid",
                quantity=1,
                total_value=10000,
                aadhar_number="123456789012",
            ),
        )

        response = self.client.post(
            reverse("ui:sequence-list"),
            {
                "action": "save_sequences",
                "session": str(session.pk),
                "item_name": ["Medical Aid"],
                "sequence_no": ["12"],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(
                models.SequenceListItem.objects.filter(session=session)
                .values_list("item_name", "sequence_no")
            ),
            [("Medical Aid", 12)],
        )
        seat_row.refresh_from_db()
        self.assertIsNone(seat_row.sequence_no)
        submit_result = self.client.session.get("sequence_submit_result")
        self.assertIsNotNone(submit_result)
        self.assertFalse(submit_result["all_matched"])
        labels = [check["label"] for check in submit_result["checks"]]
        self.assertIn("Final data integrity", labels)
        self.assertIn("Final Sequence vs Master Data", labels)
        self.assertIn("Final Sequence vs Seat Allocation", labels)

    def test_reconciliation_overview_runs_data_health_on_demand(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        article = models.Article.objects.create(
            article_name="Medical Aid",
            cost_per_unit=10000,
            item_type=models.ItemTypeChoices.AID,
            is_active=True,
        )
        models.PublicBeneficiaryEntry.objects.create(
            application_number="P001",
            name="Person 1",
            aadhar_number="123456789012",
            is_handicapped=models.HandicappedStatusChoices.NO,
            article=article,
            article_cost_per_unit=10000,
            quantity=1,
            total_amount=10000,
            status=models.BeneficiaryStatusChoices.SUBMITTED,
        )
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="P001",
            beneficiary_name="Person 1",
            district="Non-District",
            requested_item="Medical Aid",
            quantity=1,
            token_quantity=1,
            sequence_no=5,
            beneficiary_type="Public",
            item_type="Aid",
            master_headers=EXPORT_COLUMNS,
            master_row=self._public_master_row(
                application_number="P001",
                name="Person 1",
                requested_item="Medical Aid",
                quantity=1,
                total_value=10000,
                aadhar_number="123456789012",
            ),
        )
        models.SequenceListItem.objects.create(
            session=session,
            item_name="Medical Aid",
            sequence_no=5,
            sort_order=1,
            created_by=self.user,
            updated_by=self.user,
        )

        initial_response = self.client.get(reverse("ui:reconciliation-overview"), {"session": str(session.pk)})
        self.assertEqual(initial_response.status_code, 200)
        self.assertContains(initial_response, "Run Data Health")
        self.assertNotContains(initial_response, "Dashboard Metrics")

        response = self.client.post(
            reverse("ui:reconciliation-overview"),
            {"action": "run_data_health", "session": str(session.pk)},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard Metrics")
        self.assertContains(response, "Application Entry")
        self.assertContains(response, "Seat Allocation")
        self.assertContains(response, "Sequence List")
        self.assertContains(response, "Export Consistency")

    def test_seat_allocation_export_excludes_sequence_column(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="D001",
            beneficiary_name="Ariyalur",
            district="Ariyalur",
            requested_item="Education Aid",
            quantity=3,
            waiting_hall_quantity=1,
            token_quantity=2,
            beneficiary_type="District",
            item_type="Aid",
            sequence_no=7,
            master_headers=[
                "Application Number",
                "Beneficiary Name",
                "Requested Item",
                "Quantity",
                "Beneficiary Type",
                "Item Type",
            ],
            master_row={
                "Application Number": "D001",
                "Beneficiary Name": "Ariyalur",
                "Requested Item": "Education Aid",
                "Quantity": "3",
                "Beneficiary Type": "District",
                "Item Type": "Aid",
            },
        )

        response = self.client.get(
            reverse("ui:seat-allocation-list"),
            {"session": str(session.pk), "export": "1"},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        header_line = content.splitlines()[0]
        self.assertIn("Waiting Hall Quantity", header_line)
        self.assertIn("Token Quantity", header_line)
        self.assertNotIn("Sequence No", header_line)

    def test_sequence_export_keeps_plain_25_column_output(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="P001",
            beneficiary_name="Person 1",
            district="Non-District",
            requested_item="Medical Aid",
            quantity=1,
            token_quantity=1,
            beneficiary_type="Public",
            item_type="Aid",
            sequence_no=12,
            master_headers=EXPORT_COLUMNS,
            master_row={
                "Application Number": "P001",
                "Beneficiary Name": "Person 1",
                "Requested Item": "Medical Aid",
                "Quantity": "1",
                "Cost Per Unit": "10000",
                "Total Value": "10000",
                "Address": "",
                "Mobile": "",
                "Aadhar Number": "",
                "Name of Beneficiary": "Person 1",
                "Name of Institution": "",
                "Cheque / RTGS in Favour": "",
                "Handicapped Status": "",
                "Gender": "",
                "Gender Category": "",
                "Beneficiary Type": "Public",
                "Item Type": "Aid",
                "Article Category": "",
                "Super Category Article": "",
                "Token Name": "",
                "Internal Notes": "",
                "Comments": "",
            },
        )

        response = self.client.get(
            reverse("ui:sequence-list"),
            {"session": str(session.pk), "export": "1"},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8"))))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn("Names", row)
        self.assertNotIn("R_Names", row)
        self.assertEqual(row["Sequence No"], "12")
        self.assertEqual(row["Aadhar Number"], "")
        self.assertEqual(row["Name of Institution"], "")
        self.assertEqual(row["Cheque / RTGS in Favour"], "")
        self.assertEqual(row["Internal Notes"], "")

    def test_use_existing_updates_session_reconciliation_totals(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        district = models.DistrictMaster.objects.create(
            district_name="Ariyalur",
            application_number="D001",
            allotted_budget=100000,
            president_name="President",
            mobile_number="9999999999",
        )
        article = models.Article.objects.create(
            article_name="Education Aid",
            cost_per_unit=10000,
            item_type=models.ItemTypeChoices.AID,
            is_active=True,
        )
        models.DistrictBeneficiaryEntry.objects.create(
            district=district,
            application_number="D001",
            article=article,
            article_cost_per_unit=10000,
            quantity=1,
            total_amount=10000,
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            notes="E1",
        )
        models.DistrictBeneficiaryEntry.objects.create(
            district=district,
            application_number="D001",
            article=article,
            article_cost_per_unit=10000,
            quantity=2,
            total_amount=20000,
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            notes="E2",
        )

        response = self.client.post(
            reverse("ui:seat-allocation-list"),
            {"action": "use_existing", "session": str(session.pk)},
        )

        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.phase2_source_name, "master-entry-db")
        self.assertEqual(session.phase2_source_row_count, 2)
        self.assertEqual(session.phase2_grouped_row_count, 2)
        self.assertEqual(session.phase2_source_quantity_total, 3)
        self.assertEqual(session.phase2_grouped_quantity_total, 3)
        self.assertEqual(session.phase2_reconciliation_snapshot["source_total_value"], 30000)
        self.assertEqual(session.phase2_reconciliation_snapshot["grouped_total_value"], 30000)
        self.assertEqual(session.phase2_reconciliation_snapshot["source_unique_items"], 1)
        self.assertEqual(session.phase2_reconciliation_snapshot["grouped_unique_items"], 1)

    def test_token_generation_sync_applies_data_prep_and_exports_token_columns(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="P001",
            beneficiary_name="Person 1",
            district="Non-District",
            requested_item="Medical Aid",
            quantity=1,
            waiting_hall_quantity=0,
            token_quantity=1,
            beneficiary_type="Public",
            item_type="Aid",
            sequence_no=12,
            master_headers=EXPORT_COLUMNS,
            master_row={
                "Application Number": "P001",
                "Beneficiary Name": "Person 1",
                "Requested Item": "Medical Aid",
                "Quantity": "1",
                "Cost Per Unit": "10000",
                "Total Value": "10000",
                "Address": "",
                "Mobile": "",
                "Aadhar Number": "",
                "Name of Beneficiary": "Person 1",
                "Name of Institution": "",
                "Cheque / RTGS in Favour": "",
                "Handicapped Status": "",
                "Gender": "",
                "Gender Category": "",
                "Beneficiary Type": "Public",
                "Item Type": "Aid",
                "Article Category": "",
                "Super Category Article": "",
                "Token Name": "",
                "Internal Notes": "",
                "Comments": "",
            },
        )
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="I001",
            beneficiary_name="Government Leprosy Centre,Chengalpattu.",
            district="Non-District",
            requested_item="Wheel Chair",
            quantity=1,
            waiting_hall_quantity=0,
            token_quantity=2,
            beneficiary_type="Institutions",
            item_type="Article",
            sequence_no=10,
            master_headers=EXPORT_COLUMNS,
            master_row={
                "Application Number": "I001",
                "Beneficiary Name": "Government Leprosy Centre,Chengalpattu.",
                "Requested Item": "Wheel Chair",
                "Quantity": "1",
                "Cost Per Unit": "5000",
                "Total Value": "5000",
                "Address": "",
                "Mobile": "",
                "Aadhar Number": "",
                "Name of Beneficiary": "",
                "Name of Institution": "",
                "Cheque / RTGS in Favour": "",
                "Handicapped Status": "",
                "Gender": "",
                "Gender Category": "",
                "Beneficiary Type": "Institutions",
                "Item Type": "Article",
                "Article Category": "",
                "Super Category Article": "",
                "Token Name": "Wet Grinder Floor 2L",
                "Internal Notes": "",
                "Comments": "",
            },
        )

        response = self.client.post(
            reverse("ui:token-generation"),
            {"action": "sync_data", "session": str(session.pk)},
        )

        self.assertEqual(response.status_code, 302)
        saved_rows = list(models.TokenGenerationRow.objects.filter(session=session))
        self.assertEqual(len(saved_rows), 2)
        raw_first = saved_rows[0].row_data
        self.assertNotIn("Names", raw_first)
        self.assertNotIn("R_Names", raw_first)

        prep_response = self.client.post(
            reverse("ui:token-generation"),
            {"action": "run_data_prep", "session": str(session.pk)},
        )
        self.assertEqual(prep_response.status_code, 302)

        saved_rows = list(models.TokenGenerationRow.objects.filter(session=session).order_by("sort_order"))
        first_saved = saved_rows[0].row_data
        second_saved = saved_rows[1].row_data
        self.assertEqual(first_saved["Names"], "I001-Govt Leprosy Centre,CGL")
        self.assertNotIn("R_Names", first_saved)
        self.assertEqual(first_saved["Token Name"], "Wet Grinder FLR 2L")
        self.assertEqual(first_saved["Token Print for ARTL"], "1")
        self.assertNotIn("Start Token No", first_saved)
        self.assertNotIn("End Token No", first_saved)
        self.assertEqual(second_saved["Names"], "P001 - Person 1")
        self.assertNotIn("R_Names", second_saved)
        self.assertEqual(second_saved["Aadhar Number"], "0")
        self.assertEqual(second_saved["Name of Institution"], "N/A")
        self.assertNotIn("Start Token No", second_saved)
        self.assertNotIn("End Token No", second_saved)
        self.assertEqual(second_saved["Token Print for ARTL"], "0")

        sort_response = self.client.post(
            reverse("ui:token-generation"),
            {"action": "sort_data", "session": str(session.pk)},
        )
        self.assertEqual(sort_response.status_code, 302)

        save_token_print_response = self.client.post(
            reverse("ui:token-generation"),
            {"action": "save_token_print", "session": str(session.pk)},
        )
        self.assertEqual(save_token_print_response.status_code, 302)

        generate_response = self.client.post(
            reverse("ui:token-generation"),
            {"action": "generate_tokens", "session": str(session.pk)},
        )
        self.assertEqual(generate_response.status_code, 302)

        saved_rows = list(models.TokenGenerationRow.objects.filter(session=session).order_by("sort_order"))
        first_saved = saved_rows[0].row_data
        second_saved = saved_rows[1].row_data
        self.assertEqual(first_saved["Start Token No"], "1")
        self.assertEqual(first_saved["End Token No"], "2")
        self.assertEqual(second_saved["Start Token No"], "3")
        self.assertEqual(second_saved["End Token No"], "3")

        export_response = self.client.get(
            reverse("ui:token-generation"),
            {"session": str(session.pk), "export": "1"},
        )
        self.assertEqual(export_response.status_code, 200)
        export_rows = list(csv.DictReader(io.StringIO(export_response.content.decode("utf-8"))))
        self.assertEqual(len(export_rows), 2)
        export_row = export_rows[0]
        self.assertIn("Start Token No", export_row)
        self.assertIn("End Token No", export_row)
        self.assertIn("Token Print for ARTL", export_row)
        self.assertEqual(export_row["Names"], "I001-Govt Leprosy Centre,CGL")

    def test_token_generation_can_exclude_selected_rows_before_prep(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="D067",
            beneficiary_name="Additional",
            district="Additional",
            requested_item="Dell laptop Core i5",
            quantity=1,
            waiting_hall_quantity=1,
            token_quantity=0,
            beneficiary_type="District",
            item_type="Article",
            sequence_no=15,
            master_headers=EXPORT_COLUMNS,
            master_row={
                "Application Number": "D067",
                "Beneficiary Name": "Additional",
                "Requested Item": "Dell laptop Core i5",
                "Quantity": "1",
                "Cost Per Unit": "50000",
                "Total Value": "50000",
                "Address": "",
                "Mobile": "",
                "Aadhar Number": "",
                "Name of Beneficiary": "",
                "Name of Institution": "",
                "Cheque / RTGS in Favour": "",
                "Handicapped Status": "",
                "Gender": "",
                "Gender Category": "",
                "Beneficiary Type": "District",
                "Item Type": "Article",
                "Article Category": "",
                "Super Category Article": "",
                "Token Name": "",
                "Internal Notes": "",
                "Comments": "",
            },
        )
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="D001",
            beneficiary_name="Ariyalur",
            district="Ariyalur",
            requested_item="Education Aid",
            quantity=1,
            waiting_hall_quantity=0,
            token_quantity=1,
            beneficiary_type="District",
            item_type="Aid",
            sequence_no=1,
            master_headers=EXPORT_COLUMNS,
            master_row={
                "Application Number": "D001",
                "Beneficiary Name": "Ariyalur",
                "Requested Item": "Education Aid",
                "Quantity": "1",
                "Cost Per Unit": "10000",
                "Total Value": "10000",
                "Address": "",
                "Mobile": "",
                "Aadhar Number": "",
                "Name of Beneficiary": "",
                "Name of Institution": "",
                "Cheque / RTGS in Favour": "",
                "Handicapped Status": "",
                "Gender": "",
                "Gender Category": "",
                "Beneficiary Type": "District",
                "Item Type": "Aid",
                "Article Category": "",
                "Super Category Article": "",
                "Token Name": "",
                "Internal Notes": "",
                "Comments": "",
            },
        )
        self.client.post(
            reverse("ui:token-generation"),
            {"action": "sync_data", "session": str(session.pk)},
        )

        response = self.client.post(
            reverse("ui:token-generation"),
            {
                "action": "exclude_selected_rows",
                "session": str(session.pk),
                "selected_row_index": ["1"],
            },
        )

        self.assertEqual(response.status_code, 302)
        saved_rows = list(models.TokenGenerationRow.objects.filter(session=session).order_by("sort_order"))
        self.assertEqual(len(saved_rows), 1)
        self.assertEqual(saved_rows[0].beneficiary_name, "Ariyalur")

    def test_token_generation_blocks_data_prep_when_quantity_or_value_columns_are_below_one(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="P001",
            beneficiary_name="Person 1",
            district="Chengalpattu",
            requested_item="Medical Aid",
            quantity=1,
            waiting_hall_quantity=0,
            token_quantity=1,
            beneficiary_type="Public",
            item_type="Aid",
            sequence_no=1,
            master_headers=EXPORT_COLUMNS,
            master_row={
                "Application Number": "P001",
                "Beneficiary Name": "Person 1",
                "Requested Item": "Medical Aid",
                "Quantity": "1",
                "Cost Per Unit": "0",
                "Total Value": "0",
                "Address": "",
                "Mobile": "",
                "Aadhar Number": "",
                "Name of Beneficiary": "",
                "Name of Institution": "",
                "Cheque / RTGS in Favour": "",
                "Handicapped Status": "",
                "Gender": "",
                "Gender Category": "",
                "Beneficiary Type": "Public",
                "Item Type": "Aid",
                "Article Category": "",
                "Super Category Article": "",
                "Token Name": "Medical Aid",
                "Internal Notes": "",
                "Comments": "",
            },
        )
        self.client.post(
            reverse("ui:token-generation"),
            {"action": "sync_data", "session": str(session.pk)},
        )

        response = self.client.post(
            reverse("ui:token-generation"),
            {"action": "run_data_prep", "session": str(session.pk)},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Step 1 data prep is blocked.")
        self.assertContains(response, "Cost Per Unit (1)")
        self.assertContains(response, "Total Value (1)")
        saved_rows = list(models.TokenGenerationRow.objects.filter(session=session).order_by("sort_order"))
        self.assertEqual(len(saved_rows), 1)
        self.assertNotIn("Names", saved_rows[0].row_data)

    def test_token_generation_requires_step3_save_before_generating_and_persists_changes(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="I001",
            beneficiary_name="Government Leprosy Centre,Chengalpattu.",
            district="Non-District",
            requested_item="Wheel Chair",
            quantity=1,
            waiting_hall_quantity=0,
            token_quantity=2,
            beneficiary_type="Institutions",
            item_type="Article",
            sequence_no=10,
            master_headers=EXPORT_COLUMNS,
            master_row={
                "Application Number": "I001",
                "Beneficiary Name": "Government Leprosy Centre,Chengalpattu.",
                "Requested Item": "Wheel Chair",
                "Quantity": "1",
                "Cost Per Unit": "5000",
                "Total Value": "5000",
                "Address": "",
                "Mobile": "",
                "Aadhar Number": "",
                "Name of Beneficiary": "",
                "Name of Institution": "",
                "Cheque / RTGS in Favour": "",
                "Handicapped Status": "",
                "Gender": "",
                "Gender Category": "",
                "Beneficiary Type": "Institutions",
                "Item Type": "Article",
                "Article Category": "",
                "Super Category Article": "",
                "Token Name": "Wheel Chair Deluxe Model",
                "Internal Notes": "",
                "Comments": "",
            },
        )
        self.client.post(
            reverse("ui:token-generation"),
            {"action": "sync_data", "session": str(session.pk)},
        )
        self.client.post(
            reverse("ui:token-generation"),
            {"action": "run_data_prep", "session": str(session.pk)},
        )

        save_adjustments_response = self.client.post(
            reverse("ui:token-generation"),
            {
                "action": "save_adjustments",
                "session": str(session.pk),
                "replace_name__I001-Govt Leprosy Centre,CGL": "I001-Govt Leprosy Centre,CGL Short",
                "replace_token_name__Wheel Chair Deluxe Model": "Wheel Chair",
            },
        )
        self.assertEqual(save_adjustments_response.status_code, 302)

        refresh_response = self.client.get(
            reverse("ui:token-generation"),
            {"session": str(session.pk)},
        )
        self.assertEqual(refresh_response.status_code, 200)
        saved_rows = list(models.TokenGenerationRow.objects.filter(session=session).order_by("sort_order"))
        self.assertEqual(saved_rows[0].row_data["Names"], "I001-Govt Leprosy Centre,CGL Short")
        self.assertEqual(saved_rows[0].row_data["Token Name"], "Wheel Chair")

        blocked_generate_response = self.client.post(
            reverse("ui:token-generation"),
            {"action": "generate_tokens", "session": str(session.pk)},
            follow=True,
        )
        self.assertEqual(blocked_generate_response.status_code, 200)
        self.assertContains(blocked_generate_response, "Complete Step 3 token print review before generating token numbers.")
        saved_rows = list(models.TokenGenerationRow.objects.filter(session=session).order_by("sort_order"))
        self.assertNotIn("Start Token No", saved_rows[0].row_data)

        save_token_print_response = self.client.post(
            reverse("ui:token-generation"),
            {"action": "save_token_print", "session": str(session.pk)},
        )
        self.assertEqual(save_token_print_response.status_code, 302)

        generate_response = self.client.post(
            reverse("ui:token-generation"),
            {"action": "generate_tokens", "session": str(session.pk)},
        )
        self.assertEqual(generate_response.status_code, 302)
        saved_rows = list(models.TokenGenerationRow.objects.filter(session=session).order_by("sort_order"))
        self.assertEqual(saved_rows[0].row_data["Start Token No"], "1")
        self.assertEqual(saved_rows[0].row_data["End Token No"], "2")

    def test_token_generation_requires_fresh_sync_when_sequence_source_changes(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        seat_row = models.SeatAllocationRow.objects.create(
            session=session,
            application_number="P001",
            beneficiary_name="Person 1",
            district="Chengalpattu",
            requested_item="Medical Aid",
            quantity=1,
            waiting_hall_quantity=0,
            token_quantity=1,
            beneficiary_type="Public",
            item_type="Aid",
            sequence_no=1,
            master_headers=EXPORT_COLUMNS,
            master_row={
                "Application Number": "P001",
                "Beneficiary Name": "Person 1",
                "Requested Item": "Medical Aid",
                "Quantity": "1",
                "Cost Per Unit": "10000",
                "Total Value": "10000",
                "Address": "",
                "Mobile": "",
                "Aadhar Number": "",
                "Name of Beneficiary": "",
                "Name of Institution": "",
                "Cheque / RTGS in Favour": "",
                "Handicapped Status": "",
                "Gender": "",
                "Gender Category": "",
                "Beneficiary Type": "Public",
                "Item Type": "Aid",
                "Article Category": "",
                "Super Category Article": "",
                "Token Name": "Medical Aid",
                "Internal Notes": "",
                "Comments": "",
            },
        )
        self.client.post(
            reverse("ui:token-generation"),
            {"action": "sync_data", "session": str(session.pk)},
        )
        seat_row.comments = "Updated after sync"
        seat_row.save(update_fields=["comments", "updated_at"])

        response = self.client.post(
            reverse("ui:token-generation"),
            {"action": "run_data_prep", "session": str(session.pk)},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Click Sync Data first to load the latest Sequence List data before continuing.")
        saved_rows = list(models.TokenGenerationRow.objects.filter(session=session).order_by("sort_order"))
        self.assertEqual(len(saved_rows), 1)
        self.assertNotIn("Names", saved_rows[0].row_data)

    def test_labels_module_can_sync_from_token_generation_and_download_article_pdf(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        models.TokenGenerationRow.objects.create(
            session=session,
            source_file_name="Synced from Token Generation",
            application_number="I001",
            beneficiary_name="Govt School",
            requested_item="Wheel Chair",
            beneficiary_type="Institutions",
            sequence_no=1,
            start_token_no=1,
            end_token_no=2,
            headers=[
                "Application Number",
                "Beneficiary Name",
                "Requested Item",
                "Beneficiary Type",
                "Sequence No",
                "Token Quantity",
                "Token Print for ARTL",
                "Names",
                "Token Name",
                "Start Token No",
                "End Token No",
            ],
            row_data={
                "Application Number": "I001",
                "Beneficiary Name": "Govt School",
                "Requested Item": "Wheel Chair",
                "Beneficiary Type": "Institutions",
                "Sequence No": "1",
                "Token Quantity": "2",
                "Token Print for ARTL": "1",
                "Names": "I001-Govt School",
                "Token Name": "Wheel Chair",
                "Start Token No": "1",
                "End Token No": "2",
            },
            sort_order=1,
            created_by=self.user,
            updated_by=self.user,
        )

        sync_response = self.client.post(
            reverse("ui:labels"),
            {"action": "sync_data", "session": str(session.pk)},
        )
        self.assertEqual(sync_response.status_code, 302)
        saved_rows = list(models.LabelGenerationRow.objects.filter(session=session))
        self.assertEqual(len(saved_rows), 1)
        self.assertEqual(saved_rows[0].row_data["Token Name"], "Wheel Chair")

        save_selection_response = self.client.post(
            reverse("ui:labels"),
            {"action": "save_large_items", "session": str(session.pk)},
        )
        self.assertEqual(save_selection_response.status_code, 302)

        download_response = self.client.get(
            reverse("ui:labels"),
            {"session": str(session.pk), "download": "article_12l_continuous"},
        )
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response["Content-Type"], "application/pdf")
        self.assertIn(b"%PDF", download_response.content[:10])

    def test_labels_article_download_requires_2l_selection_save_first(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        models.TokenGenerationRow.objects.create(
            session=session,
            source_file_name="Synced from Token Generation",
            application_number="I001",
            beneficiary_name="Govt School",
            requested_item="Wheel Chair",
            beneficiary_type="Institutions",
            sequence_no=1,
            start_token_no=1,
            end_token_no=2,
            headers=[
                "Application Number",
                "Beneficiary Name",
                "Requested Item",
                "Beneficiary Type",
                "Sequence No",
                "Token Quantity",
                "Token Print for ARTL",
                "Names",
                "Token Name",
                "Start Token No",
                "End Token No",
            ],
            row_data={
                "Application Number": "I001",
                "Beneficiary Name": "Govt School",
                "Requested Item": "Wheel Chair",
                "Beneficiary Type": "Institutions",
                "Sequence No": "1",
                "Token Quantity": "2",
                "Token Print for ARTL": "1",
                "Names": "I001-Govt School",
                "Token Name": "Wheel Chair",
                "Start Token No": "1",
                "End Token No": "2",
            },
            sort_order=1,
            created_by=self.user,
            updated_by=self.user,
        )
        self.client.post(
            reverse("ui:labels"),
            {"action": "sync_data", "session": str(session.pk)},
        )

        response = self.client.get(
            reverse("ui:labels"),
            {"session": str(session.pk), "download": "article_12l_continuous"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select 2L Items first before downloading article labels.")

    def test_labels_module_requires_fresh_sync_when_token_data_changes(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        token_row = models.TokenGenerationRow.objects.create(
            session=session,
            source_file_name="Synced from Token Generation",
            application_number="I001",
            beneficiary_name="Govt School",
            requested_item="Wheel Chair",
            beneficiary_type="Institutions",
            sequence_no=1,
            start_token_no=1,
            end_token_no=2,
            headers=[
                "Application Number",
                "Beneficiary Name",
                "Requested Item",
                "Beneficiary Type",
                "Sequence No",
                "Token Quantity",
                "Token Print for ARTL",
                "Names",
                "Token Name",
                "Start Token No",
                "End Token No",
            ],
            row_data={
                "Application Number": "I001",
                "Beneficiary Name": "Govt School",
                "Requested Item": "Wheel Chair",
                "Beneficiary Type": "Institutions",
                "Sequence No": "1",
                "Token Quantity": "2",
                "Token Print for ARTL": "1",
                "Names": "I001-Govt School",
                "Token Name": "Wheel Chair",
                "Start Token No": "1",
                "End Token No": "2",
            },
            sort_order=1,
            created_by=self.user,
            updated_by=self.user,
        )
        self.client.post(
            reverse("ui:labels"),
            {"action": "sync_data", "session": str(session.pk)},
        )
        token_row.row_data["Token Name"] = "Wheel Chair Updated"
        token_row.updated_by = self.user
        token_row.save(update_fields=["row_data", "updated_by", "updated_at"])

        response = self.client.get(
            reverse("ui:labels"),
            {"session": str(session.pk), "download": "article_12l_continuous"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Click Sync Data first to load the latest Token Generation data before downloading labels.")

    def test_labels_download_blocks_when_token_ranges_do_not_match_expected_labels(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        models.TokenGenerationRow.objects.create(
            session=session,
            source_file_name="Synced from Token Generation",
            application_number="I001",
            beneficiary_name="Govt School",
            requested_item="Wheel Chair",
            beneficiary_type="Institutions",
            sequence_no=1,
            start_token_no=1,
            end_token_no=1,
            headers=[
                "Application Number",
                "Beneficiary Name",
                "Requested Item",
                "Beneficiary Type",
                "Sequence No",
                "Token Quantity",
                "Token Print for ARTL",
                "Names",
                "Token Name",
                "Start Token No",
                "End Token No",
            ],
            row_data={
                "Application Number": "I001",
                "Beneficiary Name": "Govt School",
                "Requested Item": "Wheel Chair",
                "Beneficiary Type": "Institutions",
                "Sequence No": "1",
                "Token Quantity": "2",
                "Token Print for ARTL": "1",
                "Names": "I001-Govt School",
                "Token Name": "Wheel Chair",
                "Start Token No": "1",
                "End Token No": "1",
            },
            sort_order=1,
            created_by=self.user,
            updated_by=self.user,
        )
        self.client.post(
            reverse("ui:labels"),
            {"action": "sync_data", "session": str(session.pk)},
        )
        self.client.post(
            reverse("ui:labels"),
            {"action": "save_large_items", "session": str(session.pk)},
        )

        response = self.client.get(
            reverse("ui:labels"),
            {"session": str(session.pk), "download": "institution"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Label check failed for this download.")

    def test_labels_module_can_download_custom_labels_pdf(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        response = self.client.post(
            reverse("ui:labels"),
            {
                "action": "download_custom_labels",
                "session": str(session.pk),
                "custom_label_text": "Special Counter",
                "custom_label_count": "3",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(b"%PDF", response.content[:10])

    def test_labels_module_upload_accepts_excel_file(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Application Number", "Names", "Requested Item", "Token Name", "Start Token No", "End Token No"])
        sheet.append(["I001", "I001-Govt School", "Wheel Chair", "Wheel Chair", 1, 2])
        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        uploaded = SimpleUploadedFile(
            "labels.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(
            reverse("ui:labels"),
            {"action": "upload_csv", "session": str(session.pk), "file": uploaded},
        )

        self.assertEqual(response.status_code, 302)
        saved_rows = list(models.LabelGenerationRow.objects.filter(session=session).order_by("sort_order"))
        self.assertEqual(len(saved_rows), 1)
        self.assertEqual(saved_rows[0].row_data["Token Name"], "Wheel Chair")
        self.assertEqual(saved_rows[0].row_data["Start Token No"], "1")

    def test_labels_module_upload_accepts_legacy_token_workbook_shape(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.append([
            "Application Number",
            "Names",
            "Beneficiary Name",
            "Requested Item",
            "Beneficiary Type",
            "Requested Item Tk",
            "Token Quantity",
            "Start Token No.",
            "End Token No.",
            "Token Print for ARTL",
        ])
        sheet.append([
            "I001",
            "I001-Govt School",
            "Govt School",
            "Wheel Chair",
            "Institutions",
            "Wheel Chair Short",
            2,
            1,
            2,
            1,
        ])
        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        uploaded = SimpleUploadedFile(
            "labels_legacy.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(
            reverse("ui:labels"),
            {"action": "upload_csv", "session": str(session.pk), "file": uploaded},
        )

        self.assertEqual(response.status_code, 302)
        saved_rows = list(models.LabelGenerationRow.objects.filter(session=session).order_by("sort_order"))
        self.assertEqual(len(saved_rows), 1)
        self.assertEqual(saved_rows[0].row_data["Token Name"], "Wheel Chair Short")
        self.assertEqual(saved_rows[0].row_data["Start Token No"], "1")
        self.assertEqual(saved_rows[0].row_data["End Token No"], "2")

        download_response = self.client.get(
            reverse("ui:labels"),
            {"session": str(session.pk), "download": "institution"},
        )
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response["Content-Type"], "application/pdf")
        self.assertIn(b"%PDF", download_response.content[:10])

    def test_use_existing_preserves_matching_split_values(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="D001",
            beneficiary_name="Ariyalur",
            district="Ariyalur",
            requested_item="Education Aid",
            quantity=3,
            waiting_hall_quantity=1,
            token_quantity=2,
            beneficiary_type="District",
            item_type="Aid",
            comments="E1",
        )
        district = models.DistrictMaster.objects.create(
            district_name="Ariyalur",
            application_number="D001",
            allotted_budget=100000,
            president_name="President",
            mobile_number="9999999999",
        )
        article = models.Article.objects.create(
            article_name="Education Aid",
            cost_per_unit=10000,
            item_type=models.ItemTypeChoices.AID,
            is_active=True,
        )
        models.DistrictBeneficiaryEntry.objects.create(
            district=district,
            application_number="D001",
            article=article,
            article_cost_per_unit=10000,
            quantity=3,
            total_amount=30000,
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            notes="E1",
        )

        response = self.client.post(
            reverse("ui:seat-allocation-list"),
            {"action": "use_existing", "session": str(session.pk)},
        )

        self.assertEqual(response.status_code, 302)
        row = models.SeatAllocationRow.objects.get(session=session, application_number="D001", requested_item="Education Aid")
        self.assertEqual(row.waiting_hall_quantity, 1)
        self.assertEqual(row.token_quantity, 2)

    def test_upload_csv_uses_waiting_hall_and_token_columns_when_present(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        csv_content = (
            "Application Number,Beneficiary Name,Requested Item,Quantity,Beneficiary Type,Item Type,Comments,Total Value,Waiting Hall Quantity,Token Quantity\n"
            "D001,Ariyalur,Education Aid,3,District,Aid,E1,30000,1,2\n"
        )
        uploaded = SimpleUploadedFile("seat-allocation.csv", csv_content.encode("utf-8"), content_type="text/csv")

        response = self.client.post(
            reverse("ui:seat-allocation-list"),
            {"action": "upload_csv", "session": str(session.pk), "file": uploaded},
        )

        self.assertEqual(response.status_code, 302)
        row = models.SeatAllocationRow.objects.get(session=session, application_number="D001", requested_item="Education Aid")
        self.assertEqual(row.waiting_hall_quantity, 1)
        self.assertEqual(row.token_quantity, 2)

    def test_master_change_state_marks_matching_identity_with_changed_values_as_updated(self):
        session = models.EventSession.objects.create(session_name="2026 Event", event_year=2026, is_active=True)
        models.SeatAllocationRow.objects.create(
            session=session,
            application_number="D001",
            beneficiary_name="Ariyalur",
            district="Ariyalur",
            requested_item="Education Aid",
            quantity=1,
            token_quantity=1,
            beneficiary_type="District",
            item_type="Aid",
            comments="Old comments",
            master_headers=[
                "Application Number",
                "Beneficiary Name",
                "Requested Item",
                "Quantity",
                "Beneficiary Type",
                "Item Type",
                "Comments",
                "Total Value",
            ],
            master_row={
                "Application Number": "D001",
                "Beneficiary Name": "Ariyalur",
                "Requested Item": "Education Aid",
                "Quantity": "1",
                "Beneficiary Type": "District",
                "Item Type": "Aid",
                "Comments": "Old comments",
                "Total Value": "10000",
            },
        )

        state = _phase2_master_change_state(
            session,
            [
                {
                    "application_number": "D001",
                    "beneficiary_name": "Ariyalur",
                    "district": "Ariyalur",
                    "requested_item": "Education Aid",
                    "quantity": 2,
                    "beneficiary_type": "District",
                    "item_type": "Aid",
                    "comments": "Updated comments",
                    "master_row": {
                        "Application Number": "D001",
                        "Beneficiary Name": "Ariyalur",
                        "Requested Item": "Education Aid",
                        "Quantity": "2",
                        "Beneficiary Type": "District",
                        "Item Type": "Aid",
                        "Comments": "Updated comments",
                        "Total Value": "20000",
                    },
                }
            ],
        )

        self.assertTrue(state["has_changes"])
        self.assertEqual(state["new_count"], 0)
        self.assertEqual(state["removed_count"], 0)
        self.assertEqual(state["updated_count"], 1)
        self.assertIn("Quantity 1 -> 2", state["updated_rows"][0]["changes"])
