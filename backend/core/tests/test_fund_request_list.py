from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import models
from core.order_fund_request import services


class FundRequestListRegressionTests(TestCase):
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
            cost_per_unit=Decimal("44100.00"),
            item_type=models.ItemTypeChoices.ARTICLE,
            combo=False,
            is_active=True,
        )
        self.aid_article = models.Article.objects.create(
            article_name="Medical Aid",
            cost_per_unit=Decimal("8000.00"),
            item_type=models.ItemTypeChoices.AID,
            combo=False,
            is_active=True,
        )
        self.district = models.DistrictMaster.objects.create(
            district_name="Chengalpattu",
            allotted_budget=Decimal("100000.00"),
            president_name="President",
            mobile_number="9876543210",
            application_number="D001",
            is_active=True,
        )

    def _create_fund_request(self, *, number: str, created_at, aid_type: str = "Medical Aid", total_amount: int = 80000):
        return models.FundRequest.objects.create(
            fund_request_type=models.FundRequestTypeChoices.AID,
            fund_request_number=number,
            status=models.FundRequestStatusChoices.SUBMITTED,
            total_amount=total_amount,
            aid_type=aid_type,
            created_by=self.user,
            created_at=created_at,
        )

    def _add_recipients(self, fund_request: models.FundRequest, count: int, *, details_prefix: str = "Recipient"):
        for index in range(count):
            models.FundRequestRecipient.objects.create(
                fund_request=fund_request,
                beneficiary_type=models.RecipientTypeChoices.PUBLIC,
                recipient_name=f"Person {index + 1}",
                name_of_beneficiary=f"Person {index + 1}",
                details=f"{details_prefix} {index + 1}",
                fund_requested=10000,
                aadhar_number=f"{index + 1:012d}",
                cheque_in_favour=f"Payee {index + 1}",
            )

    def _create_district_aid_entry(self):
        return models.DistrictBeneficiaryEntry.objects.create(
            district=self.district,
            application_number="D001",
            article=self.aid_article,
            article_cost_per_unit=Decimal("8000.00"),
            quantity=1,
            total_amount=Decimal("8000.00"),
            aadhar_number="111122223333",
            name_of_beneficiary="Student Alpha",
            name_of_institution="Govt School",
            cheque_rtgs_in_favour="District Payee",
            notes="Scholarship detail",
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            created_by=self.user,
        )

    def _create_public_aid_entry(self, *, aadhaar_status, aadhar_number="123456789012"):
        return models.PublicBeneficiaryEntry.objects.create(
            application_number="P001",
            name="Public Alpha",
            mobile="9876543210",
            address="Chennai",
            article=self.aid_article,
            article_cost_per_unit=Decimal("8000.00"),
            quantity=1,
            total_amount=Decimal("8000.00"),
            aadhar_number=aadhar_number if aadhaar_status == models.AadhaarVerificationStatusChoices.VERIFIED else "",
            aadhaar_status=aadhaar_status,
            name_of_institution="",
            cheque_rtgs_in_favour="Public Payee",
            notes="Medical aid",
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            created_by=self.user,
        )

    def test_submitted_list_shows_each_fund_request_once_with_multiple_recipients(self):
        fr5 = self._create_fund_request(number="FR-005", created_at=timezone.now())
        self._add_recipients(fr5, 4, details_prefix="Medical detail")

        fr6 = self._create_fund_request(number="FR-006", created_at=timezone.now() + timezone.timedelta(minutes=5), total_amount=44100)
        models.FundRequestArticle.objects.create(
            fund_request=fr6,
            article=self.article,
            article_name="Wheelchair",
            quantity=1,
            unit_price=44100,
            price_including_gst=44100,
            value=44100,
            cumulative=44100,
        )

        response = self.client.get(
            reverse("ui:fund-request-list"),
            {"status": "submitted", "sort": "created_at", "dir": "desc"},
        )

        self.assertEqual(response.status_code, 200)
        ids = [fund_request.id for fund_request in response.context["fund_requests"]]
        self.assertEqual(ids, [fr6.id, fr5.id])
        self.assertEqual(ids.count(fr5.id), 1)

    def test_global_search_returns_matching_request_once_even_with_multiple_related_rows(self):
        fr5 = self._create_fund_request(number="FR-005", created_at=timezone.now())
        self._add_recipients(fr5, 4, details_prefix="df marker")

        response = self.client.get(
            reverse("ui:fund-request-list"),
            {"q": "df marker", "status": "submitted", "sort": "created_at", "dir": "desc"},
        )

        self.assertEqual(response.status_code, 200)
        ids = [fund_request.id for fund_request in response.context["fund_requests"]]
        self.assertEqual(ids, [fr5.id])
        self.assertEqual(ids.count(fr5.id), 1)

    def test_next_fund_request_number_uses_three_digit_padding(self):
        self._create_fund_request(number="FR-009", created_at=timezone.now())
        self._create_fund_request(number="FR-010", created_at=timezone.now() + timezone.timedelta(minutes=1))

        self.assertEqual(services.next_fund_request_number(), "FR-011")

    def test_existing_single_digit_numbers_render_with_padding(self):
        fr = self._create_fund_request(number="FR-2", created_at=timezone.now())

        self.assertEqual(fr.formatted_fund_request_number, "FR-002")

    def test_district_aid_options_reflect_latest_saved_entry_fields(self):
        entry = self._create_district_aid_entry()
        entry.aadhar_number = "999900001111"
        entry.name_of_beneficiary = "Student Beta"
        entry.name_of_institution = "Girls Higher Secondary School"
        entry.cheque_rtgs_in_favour = "Updated District Payee"
        entry.notes = "Updated scholarship detail"
        entry.save()

        response = self.client.get(
            reverse("ui:fund-request-aid-options"),
            {
                "aid_type": self.aid_article.article_name,
                "beneficiary_type": models.RecipientTypeChoices.DISTRICT,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["options"]), 1)
        option = payload["options"][0]
        self.assertEqual(option["aadhar_number"], "999900001111")
        self.assertEqual(option["name_of_beneficiary"], "Student Beta")
        self.assertEqual(option["name_of_institution"], "Girls Higher Secondary School")
        self.assertEqual(option["cheque_in_favour"], "Updated District Payee")
        self.assertEqual(option["details"], "Updated scholarship detail")

    def test_fund_request_edit_preserves_saved_recipient_values_on_reopen(self):
        source_entry = self._create_district_aid_entry()
        fund_request = models.FundRequest.objects.create(
            fund_request_type=models.FundRequestTypeChoices.AID,
            status=models.FundRequestStatusChoices.DRAFT,
            aid_type=self.aid_article.article_name,
            total_amount=Decimal("9000.00"),
            created_by=self.user,
        )
        models.FundRequestRecipient.objects.create(
            fund_request=fund_request,
            beneficiary_type=models.RecipientTypeChoices.DISTRICT,
            source_entry_id=source_entry.id,
            beneficiary=f"{source_entry.application_number} - {self.district.district_name}",
            recipient_name="Saved Draft Recipient",
            name_of_beneficiary="Saved Draft Beneficiary",
            name_of_institution="Saved Draft Institution",
            details="Saved draft details",
            fund_requested=Decimal("9000.00"),
            aadhar_number="123123123123",
            cheque_in_favour="Saved Draft Payee",
            district_name=self.district.district_name,
        )

        response = self.client.get(reverse("ui:fund-request-edit", args=[fund_request.id]))

        self.assertEqual(response.status_code, 200)
        form = response.context["recipient_formset"].forms[0]
        self.assertEqual(form["name_of_beneficiary"].value(), "Saved Draft Beneficiary")
        self.assertEqual(form["name_of_institution"].value(), "Saved Draft Institution")
        self.assertEqual(form["aadhar_number"].value(), "123123123123")
        self.assertEqual(form["details"].value(), "Saved draft details")
        self.assertEqual(form["cheque_in_favour"].value(), "Saved Draft Payee")
        self.assertContains(response, "loadAidOptions(row, true);")

    def test_fund_request_edit_preserves_saved_article_selection_on_draft_reopen(self):
        fund_request = models.FundRequest.objects.create(
            fund_request_type=models.FundRequestTypeChoices.ARTICLE,
            status=models.FundRequestStatusChoices.DRAFT,
            total_amount=Decimal("44100.00"),
            created_by=self.user,
        )
        models.FundRequestArticle.objects.create(
            fund_request=fund_request,
            article=self.article,
            article_name=self.article.article_name,
            supplier_article_name="Wheelchair Vendor Label",
            description="Wheelchair order",
            quantity=1,
            unit_price=Decimal("44100.00"),
            price_including_gst=Decimal("44100.00"),
            value=Decimal("44100.00"),
            cumulative=Decimal("44100.00"),
        )

        response = self.client.get(reverse("ui:fund-request-edit", args=[fund_request.id]))

        self.assertEqual(response.status_code, 200)
        form = response.context["article_formset"].forms[0]
        self.assertEqual(form["article_name"].value(), self.article.article_name)
        self.assertIn((self.article.article_name, self.article.article_name), list(form.fields["article_name"].choices))
        self.assertContains(response, self.article.article_name)

    def test_public_aid_options_exclude_aadhaar_not_available_entries(self):
        self._create_public_aid_entry(aadhaar_status=models.AadhaarVerificationStatusChoices.NOT_AVAILABLE, aadhar_number="")

        response = self.client.get(
            reverse("ui:fund-request-aid-options"),
            {
                "aid_type": self.aid_article.article_name,
                "beneficiary_type": models.RecipientTypeChoices.PUBLIC,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["options"], [])

    def test_public_aid_submit_blocks_aadhaar_not_available_without_number(self):
        entry = self._create_public_aid_entry(aadhaar_status=models.AadhaarVerificationStatusChoices.NOT_AVAILABLE, aadhar_number="")

        response = self.client.post(
            reverse("ui:fund-request-create"),
            {
                "fund_request_type": models.FundRequestTypeChoices.AID,
                "aid_type": self.aid_article.article_name,
                "action": "submit",
                "recipients-TOTAL_FORMS": "1",
                "recipients-INITIAL_FORMS": "0",
                "recipients-MIN_NUM_FORMS": "0",
                "recipients-MAX_NUM_FORMS": "1000",
                "recipients-0-beneficiary_type": models.RecipientTypeChoices.PUBLIC,
                "recipients-0-beneficiary": f"{entry.application_number} - {entry.name}",
                "recipients-0-source_entry_id": str(entry.pk),
                "recipients-0-recipient_name": entry.name,
                "recipients-0-name_of_beneficiary": entry.name,
                "recipients-0-name_of_institution": "Self",
                "recipients-0-details": entry.notes,
                "recipients-0-fund_requested": "8000",
                "recipients-0-aadhar_number": "",
                "recipients-0-address": entry.address,
                "recipients-0-cheque_in_favour": entry.cheque_rtgs_in_favour,
                "recipients-0-cheque_no": "",
                "recipients-0-notes": entry.notes,
                "recipients-0-district_name": "",
                "articles-TOTAL_FORMS": "0",
                "articles-INITIAL_FORMS": "0",
                "articles-MIN_NUM_FORMS": "0",
                "articles-MAX_NUM_FORMS": "1000",
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["recipient_formset"].forms[0]
        self.assertIn("beneficiary", form.errors)
        self.assertIn("This application does not have a verified Aadhaar.", form.errors["beneficiary"][0])
