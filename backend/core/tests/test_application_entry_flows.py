from __future__ import annotations

import csv
import io
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core import models


class ApplicationEntryFlowTests(TestCase):
    def setUp(self):
        self.user = models.AppUser.objects.create_superuser(
            email="admin@example.com",
            password="testpass123",
            role=models.RoleChoices.ADMIN,
            status=models.StatusChoices.ACTIVE,
        )
        self.client.force_login(self.user)

        self.article = models.Article.objects.create(
            article_name="Wheelchair",
            article_name_tk="Wheel Token",
            cost_per_unit=Decimal("5000.00"),
            item_type=models.ItemTypeChoices.ARTICLE,
            category="Mobility",
            master_category="Medical",
            combo=False,
            is_active=True,
        )
        self.aid_article = models.Article.objects.create(
            article_name="Education Aid",
            article_name_tk="Education Token",
            cost_per_unit=Decimal("6000.00"),
            item_type=models.ItemTypeChoices.AID,
            category="Scholarship",
            master_category="Support",
            combo=False,
            is_active=True,
        )
        self.district = models.DistrictMaster.objects.create(
            district_name="Ariyalur",
            allotted_budget=Decimal("100000.00"),
            president_name="District President",
            mobile_number="9876543210",
            application_number="D001",
            is_active=True,
        )

    def _district_payload(
        self,
        *,
        action: str = "draft",
        entry_id: str = "",
        article_id: int | None = None,
        quantity: str = "2",
        unit_cost: str = "6000.00",
        notes: str = "District note",
        name_of_beneficiary: str = "Student A",
        name_of_institution: str = "Govt School",
        aadhar_number: str = "123412341234",
        cheque_rtgs_in_favour: str = "District Payee",
    ):
        return {
            "district_id": str(self.district.id),
            "action": action,
            "internal_notes": "District internal",
            "entry_id": [entry_id],
            "article_id": [str(article_id or self.aid_article.id)],
            "quantity": [quantity],
            "unit_cost": [unit_cost],
            "notes": [notes],
            "name_of_beneficiary": [name_of_beneficiary],
            "name_of_institution": [name_of_institution],
            "aadhar_number": [aadhar_number],
            "cheque_rtgs_in_favour": [cheque_rtgs_in_favour],
        }

    def _public_payload(self, *, action: str = "draft", quantity: str = "2"):
        return {
            "action": action,
            "aadhar_number": "123456789012",
            "name": "Public Beneficiary",
            "is_handicapped": "false",
            "disability_category": "",
            "gender": models.GenderChoices.FEMALE,
            "female_status": models.FemaleStatusChoices.WIDOWED,
            "address": "Public Address",
            "mobile": "9999999999",
            "article_id": str(self.aid_article.id),
            "article_cost_per_unit": "6000.00",
            "quantity": quantity,
            "name_of_institution": "Public Trust",
            "cheque_rtgs_in_favour": "Public Payee",
            "notes": "Public note",
        }

    def _institution_payload(
        self,
        *,
        action: str = "draft",
        entry_id: str = "",
        quantity: str = "3",
        unit_cost: str = "5000.00",
    ):
        return {
            "action": action,
            "institution_name": "SRV School",
            "institution_type": models.InstitutionTypeChoices.OTHERS,
            "address": "Institution Address",
            "mobile": "8888888888",
            "internal_notes": "Institution internal",
            "entry_id": [entry_id],
            "article_id": [str(self.article.id)],
            "quantity": [quantity],
            "unit_cost": [unit_cost],
            "notes": ["Institution note"],
            "name_of_beneficiary": [""],
            "name_of_institution": ["Institution Wing"],
            "aadhar_number": ["555566667777"],
            "cheque_rtgs_in_favour": ["Institution Payee"],
        }

    def test_master_entry_view_reports_counts_and_total_rows(self):
        models.DistrictBeneficiaryEntry.objects.create(
            district=self.district,
            application_number="D001",
            article=self.aid_article,
            article_cost_per_unit=Decimal("6000.00"),
            quantity=2,
            total_amount=Decimal("12000.00"),
            status=models.BeneficiaryStatusChoices.DRAFT,
            created_by=self.user,
        )
        models.PublicBeneficiaryEntry.objects.create(
            application_number="P001",
            name="Public Beneficiary",
            aadhar_number="123456789012",
            is_handicapped=models.HandicappedStatusChoices.NO,
            gender=models.GenderChoices.MALE,
            address="Public Address",
            mobile="9999999999",
            article=self.article,
            article_cost_per_unit=Decimal("5000.00"),
            quantity=1,
            total_amount=Decimal("5000.00"),
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            created_by=self.user,
        )
        models.InstitutionsBeneficiaryEntry.objects.create(
            institution_name="SRV School",
            institution_type=models.InstitutionTypeChoices.OTHERS,
            application_number="I001",
            address="Institution Address",
            mobile="8888888888",
            article=self.article,
            article_cost_per_unit=Decimal("5000.00"),
            quantity=4,
            total_amount=Decimal("20000.00"),
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            created_by=self.user,
        )

        response = self.client.get(reverse("ui:master-entry"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["district_count"], 1)
        self.assertEqual(response.context["public_count"], 1)
        self.assertEqual(response.context["institution_count"], 1)
        self.assertEqual(response.context["total_material_rows"], 3)
        self.assertEqual(response.context["grouped_material_rows"], 3)

    def test_district_entry_flow_create_update_submit_detail_reopen_delete(self):
        create_response = self.client.post(
            reverse("ui:master-entry-district-create"),
            self._district_payload(action="draft"),
        )

        self.assertRedirects(
            create_response,
            reverse("ui:master-entry-district-edit", kwargs={"district_id": self.district.id}),
        )
        entry = models.DistrictBeneficiaryEntry.objects.get(district=self.district)
        self.assertEqual(entry.status, models.BeneficiaryStatusChoices.DRAFT)
        self.assertEqual(entry.quantity, 2)
        self.assertEqual(entry.total_amount, Decimal("12000.00"))
        self.assertEqual(entry.aadhar_number, "123412341234")

        update_response = self.client.post(
            reverse("ui:master-entry-district-edit", kwargs={"district_id": self.district.id}),
            {
                **self._district_payload(
                    action="submit",
                    entry_id=str(entry.id),
                    quantity="3",
                    unit_cost="6500.00",
                    notes="Updated district note",
                    name_of_beneficiary="Student B",
                    aadhar_number="777788889999",
                ),
                "_conflict_token": "",
            },
        )

        self.assertRedirects(update_response, reverse("ui:master-entry"))
        entry.refresh_from_db()
        self.assertEqual(entry.status, models.BeneficiaryStatusChoices.SUBMITTED)
        self.assertEqual(entry.quantity, 3)
        self.assertEqual(entry.total_amount, Decimal("19500.00"))
        self.assertEqual(entry.name_of_beneficiary, "Student B")
        self.assertEqual(entry.aadhar_number, "777788889999")

        detail_response = self.client.get(
            reverse("ui:master-entry-district-detail", kwargs={"district_id": self.district.id})
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.context["total_quantity"], 3)
        self.assertEqual(detail_response.context["total_accrued"], Decimal("19500.00"))
        self.assertEqual(detail_response.context["remaining_fund"], Decimal("80500.00"))

        reopen_response = self.client.post(
            reverse("ui:master-entry-district-reopen", kwargs={"district_id": self.district.id})
        )
        self.assertRedirects(reopen_response, reverse("ui:master-entry"))
        entry.refresh_from_db()
        self.assertEqual(entry.status, models.BeneficiaryStatusChoices.DRAFT)

        delete_response = self.client.post(
            reverse("ui:master-entry-district-delete", kwargs={"district_id": self.district.id})
        )
        self.assertRedirects(delete_response, reverse("ui:master-entry"))
        self.assertFalse(models.DistrictBeneficiaryEntry.objects.filter(district=self.district).exists())

    def test_district_detail_supports_sorting(self):
        models.DistrictBeneficiaryEntry.objects.create(
            district=self.district,
            application_number="D001",
            article=self.article,
            article_cost_per_unit=Decimal("5000.00"),
            quantity=1,
            total_amount=Decimal("5000.00"),
            status=models.BeneficiaryStatusChoices.DRAFT,
            created_by=self.user,
            name_of_beneficiary="Alpha",
        )
        models.DistrictBeneficiaryEntry.objects.create(
            district=self.district,
            application_number="D001",
            article=self.aid_article,
            article_cost_per_unit=Decimal("6000.00"),
            quantity=4,
            total_amount=Decimal("24000.00"),
            status=models.BeneficiaryStatusChoices.DRAFT,
            created_by=self.user,
            name_of_beneficiary="Zulu",
        )

        response = self.client.get(
            reverse("ui:master-entry-district-detail", kwargs={"district_id": self.district.id}),
            {"sort": "quantity", "dir": "desc"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([entry.quantity for entry in response.context["entries"]], [4, 1])
        self.assertEqual(response.context["current_sort"], "quantity")
        self.assertEqual(response.context["current_dir"], "desc")

    def test_public_entry_flow_create_update_submit_detail_reopen_delete(self):
        create_response = self.client.post(
            reverse("ui:master-entry-public-create"),
            self._public_payload(action="draft"),
        )
        created = models.PublicBeneficiaryEntry.objects.get()
        self.assertRedirects(
            create_response,
            reverse("ui:master-entry-public-edit", kwargs={"pk": created.pk}),
        )
        self.assertTrue(created.application_number.startswith("DRAFT-PUB-"))
        self.assertEqual(created.status, models.BeneficiaryStatusChoices.DRAFT)
        self.assertEqual(created.total_amount, Decimal("12000.00"))

        update_response = self.client.post(
            reverse("ui:master-entry-public-edit", kwargs={"pk": created.pk}),
            {
                **self._public_payload(action="submit", quantity="3"),
                "_conflict_token": "",
            },
        )

        self.assertRedirects(update_response, reverse("ui:master-entry") + "?type=public")
        created.refresh_from_db()
        self.assertEqual(created.application_number, "P001")
        self.assertEqual(created.status, models.BeneficiaryStatusChoices.SUBMITTED)
        self.assertEqual(created.total_amount, Decimal("18000.00"))
        self.assertEqual(created.name_of_institution, "Public Trust")

        detail_response = self.client.get(
            reverse("ui:master-entry-public-detail", kwargs={"pk": created.pk})
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.context["entry"].pk, created.pk)

        reopen_response = self.client.post(
            reverse("ui:master-entry-public-reopen", kwargs={"pk": created.pk})
        )
        self.assertRedirects(reopen_response, reverse("ui:master-entry") + "?type=public")
        created.refresh_from_db()
        self.assertEqual(created.status, models.BeneficiaryStatusChoices.DRAFT)

        delete_response = self.client.post(
            reverse("ui:master-entry-public-delete", kwargs={"pk": created.pk})
        )
        self.assertRedirects(delete_response, reverse("ui:master-entry") + "?type=public")
        self.assertFalse(models.PublicBeneficiaryEntry.objects.filter(pk=created.pk).exists())

    def test_public_detail_exposes_sortable_detail_entries(self):
        entry = models.PublicBeneficiaryEntry.objects.create(
            application_number="P001",
            name="Public Beneficiary",
            aadhar_number="123456789012",
            is_handicapped=models.HandicappedStatusChoices.NO,
            gender=models.GenderChoices.MALE,
            address="Public Address",
            mobile="9999999999",
            article=self.article,
            article_cost_per_unit=Decimal("5000.00"),
            quantity=1,
            total_amount=Decimal("5000.00"),
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            created_by=self.user,
            name_of_institution="Public Trust",
        )

        response = self.client.get(
            reverse("ui:master-entry-public-detail", kwargs={"pk": entry.pk}),
            {"sort": "name_of_institution", "dir": "asc"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["detail_entries"]), [entry])
        self.assertEqual(response.context["current_sort"], "name_of_institution")
        self.assertEqual(response.context["current_dir"], "asc")

    def test_institution_entry_flow_create_update_submit_detail_reopen_delete(self):
        create_response = self.client.post(
            reverse("ui:master-entry-institution-create"),
            self._institution_payload(action="draft"),
        )

        created = models.InstitutionsBeneficiaryEntry.objects.get()
        draft_number = created.application_number
        self.assertTrue(draft_number.startswith("DRAFT-INS-"))
        self.assertRedirects(
            create_response,
            reverse("ui:master-entry-institution-edit", kwargs={"application_number": draft_number}),
        )
        self.assertEqual(created.status, models.BeneficiaryStatusChoices.DRAFT)
        self.assertEqual(created.total_amount, Decimal("15000.00"))

        update_response = self.client.post(
            reverse("ui:master-entry-institution-edit", kwargs={"application_number": draft_number}),
            {
                **self._institution_payload(
                    action="submit",
                    entry_id=str(created.id),
                    quantity="4",
                    unit_cost="5500.00",
                ),
                "_conflict_token": "",
            },
        )

        self.assertRedirects(update_response, reverse("ui:master-entry") + "?type=institutions")
        created.refresh_from_db()
        self.assertEqual(created.application_number, "I001")
        self.assertEqual(created.status, models.BeneficiaryStatusChoices.SUBMITTED)
        self.assertEqual(created.total_amount, Decimal("22000.00"))

        detail_response = self.client.get(
            reverse("ui:master-entry-institution-detail", kwargs={"application_number": created.application_number})
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.context["total_quantity"], 4)
        self.assertEqual(detail_response.context["total_value"], Decimal("22000.00"))

        reopen_response = self.client.post(
            reverse("ui:master-entry-institution-reopen", kwargs={"application_number": created.application_number})
        )
        self.assertRedirects(reopen_response, reverse("ui:master-entry") + "?type=institutions")
        created.refresh_from_db()
        self.assertEqual(created.status, models.BeneficiaryStatusChoices.DRAFT)

        delete_response = self.client.post(
            reverse("ui:master-entry-institution-delete", kwargs={"application_number": created.application_number})
        )
        self.assertRedirects(delete_response, reverse("ui:master-entry") + "?type=institutions")
        self.assertFalse(
            models.InstitutionsBeneficiaryEntry.objects.filter(application_number=created.application_number).exists()
        )

    def test_institution_detail_supports_sorting(self):
        models.InstitutionsBeneficiaryEntry.objects.create(
            institution_name="SRV School",
            institution_type=models.InstitutionTypeChoices.OTHERS,
            application_number="I001",
            address="Institution Address",
            mobile="8888888888",
            article=self.article,
            article_cost_per_unit=Decimal("5000.00"),
            quantity=2,
            total_amount=Decimal("10000.00"),
            status=models.BeneficiaryStatusChoices.DRAFT,
            created_by=self.user,
            name_of_beneficiary="Zulu",
        )
        models.InstitutionsBeneficiaryEntry.objects.create(
            institution_name="SRV School",
            institution_type=models.InstitutionTypeChoices.OTHERS,
            application_number="I001",
            address="Institution Address",
            mobile="8888888888",
            article=self.aid_article,
            article_cost_per_unit=Decimal("6000.00"),
            quantity=1,
            total_amount=Decimal("6000.00"),
            status=models.BeneficiaryStatusChoices.DRAFT,
            created_by=self.user,
            name_of_beneficiary="Alpha",
        )

        response = self.client.get(
            reverse("ui:master-entry-institution-detail", kwargs={"application_number": "I001"}),
            {"sort": "name_of_beneficiary", "dir": "asc"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [entry.name_of_beneficiary for entry in response.context["entries"]],
            ["Alpha", "Zulu"],
        )
        self.assertEqual(response.context["current_sort"], "name_of_beneficiary")
        self.assertEqual(response.context["current_dir"], "asc")

    def test_master_entry_export_all_uses_expected_status_label_and_rows(self):
        models.DistrictBeneficiaryEntry.objects.create(
            district=self.district,
            application_number="D001",
            article=self.aid_article,
            article_cost_per_unit=Decimal("6000.00"),
            quantity=1,
            total_amount=Decimal("6000.00"),
            aadhar_number="111122223333",
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            created_by=self.user,
        )
        models.PublicBeneficiaryEntry.objects.create(
            application_number="P001",
            name="Public Beneficiary",
            aadhar_number="123456789012",
            is_handicapped=models.HandicappedStatusChoices.NO,
            gender=models.GenderChoices.MALE,
            address="Public Address",
            mobile="9999999999",
            article=self.article,
            article_cost_per_unit=Decimal("5000.00"),
            quantity=1,
            total_amount=Decimal("5000.00"),
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            created_by=self.user,
        )
        models.InstitutionsBeneficiaryEntry.objects.create(
            institution_name="SRV School",
            institution_type=models.InstitutionTypeChoices.OTHERS,
            application_number="I001",
            address="Institution Address",
            mobile="8888888888",
            article=self.article,
            article_cost_per_unit=Decimal("5000.00"),
            quantity=1,
            total_amount=Decimal("5000.00"),
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            created_by=self.user,
        )

        response = self.client.get(reverse("ui:master-entry"), {"export_scope": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("1_Master_Data_Submitted_", response["Content-Disposition"])
        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8"))))
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["Application Number"] for row in rows}, {"D001", "P001", "I001"})
