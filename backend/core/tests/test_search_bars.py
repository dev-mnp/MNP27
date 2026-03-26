from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core import models


class SearchBarSmokeTests(TestCase):
    def setUp(self):
        self.user = models.AppUser.objects.create_superuser(
            email="admin@example.com",
            password="testpass123",
            first_name="Audit",
            last_name="Tester",
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
            cost_per_unit=Decimal("6000.00"),
            item_type=models.ItemTypeChoices.AID,
            category="Aid",
            master_category="Support",
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
        models.DistrictBeneficiaryEntry.objects.create(
            district=self.district,
            application_number="D001",
            article=self.aid_article,
            article_cost_per_unit=Decimal("6000.00"),
            quantity=1,
            total_amount=Decimal("6000.00"),
            name_of_institution="District Hospital",
            cheque_rtgs_in_favour="District Payee",
            notes="District scholarship",
            internal_notes="District internal note",
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            created_by=self.user,
        )
        models.PublicBeneficiaryEntry.objects.create(
            application_number="P001",
            name="Public Beneficiary",
            aadhar_number="123456789012",
            is_handicapped=models.HandicappedStatusChoices.NO,
            gender=models.GenderChoices.FEMALE,
            female_status=models.FemaleStatusChoices.WIDOWED,
            address="Public Address",
            mobile="9999999999",
            article=self.aid_article,
            article_cost_per_unit=Decimal("6000.00"),
            quantity=1,
            total_amount=Decimal("6000.00"),
            name_of_institution="Public Trust",
            cheque_rtgs_in_favour="Public Payee",
            notes="Public note",
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            created_by=self.user,
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
            name_of_institution="Institution Wing",
            cheque_rtgs_in_favour="Institution Payee",
            notes="Institution note",
            internal_notes="Institution internal note",
            status=models.BeneficiaryStatusChoices.SUBMITTED,
            created_by=self.user,
        )
        self.fund_request = models.FundRequest.objects.create(
            fund_request_type=models.FundRequestTypeChoices.AID,
            fund_request_number="FR-001",
            status=models.FundRequestStatusChoices.SUBMITTED,
            total_amount=Decimal("6000.00"),
            aid_type="Education Aid",
            notes="Fund note",
            created_by=self.user,
        )
        models.FundRequestRecipient.objects.create(
            fund_request=self.fund_request,
            beneficiary_type=models.RecipientTypeChoices.PUBLIC,
            recipient_name="Public Beneficiary",
            name_of_beneficiary="Public Beneficiary",
            name_of_institution="Public Trust",
            details="District scholarship",
            fund_requested=Decimal("6000.00"),
            aadhar_number="123456789012",
            cheque_in_favour="Public Payee",
            district_name="Chengalpattu",
        )
        models.AuditLog.objects.create(
            user=self.user,
            action_type=models.ActionTypeChoices.CREATE,
            entity_type="public_application",
            entity_id="P001",
            details={"note": "created"},
        )

    def test_search_pages_accept_query_params(self):
        search_requests = [
            (reverse("ui:article-list"), {"q": "wheel"}),
            (reverse("ui:user-list"), {"q": "tester"}),
            (reverse("ui:application-audit-logs"), {"q": "tester"}),
            (reverse("ui:master-entry"), {"type": "district", "q": "district"}),
            (reverse("ui:master-entry"), {"type": "public", "q": "public"}),
            (reverse("ui:master-entry"), {"type": "institutions", "q": "institution"}),
            (reverse("ui:order-management"), {"q": "wheelchair"}),
            (reverse("ui:fund-request-list"), {"q": "FR-001"}),
        ]

        for url, params in search_requests:
            with self.subTest(url=url, params=params):
                response = self.client.get(url, params)
                self.assertEqual(response.status_code, 200)

    def test_district_master_entry_search_matches_institution_name_field(self):
        response = self.client.get(
            reverse("ui:master-entry"),
            {"type": "district", "q": "district hospital"},
        )

        self.assertEqual(response.status_code, 200)
        district_names = [row["district_name"] for row in response.context["district_groups"]]
        self.assertEqual(district_names, ["Chengalpattu"])

    def test_institution_master_entry_search_matches_nested_aid_fields(self):
        response = self.client.get(
            reverse("ui:master-entry"),
            {"type": "institutions", "q": "institution payee"},
        )

        self.assertEqual(response.status_code, 200)
        application_numbers = [row["application_number"] for row in response.context["institution_groups"]]
        self.assertEqual(application_numbers, ["I001"])

    def test_audit_log_search_matches_user_last_name(self):
        response = self.client.get(
            reverse("ui:application-audit-logs"),
            {"q": "tester"},
        )

        self.assertEqual(response.status_code, 200)
        logs = list(response.context["page_obj"].object_list)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].user_id, self.user.id)
