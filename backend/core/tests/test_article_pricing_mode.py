from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core import models
from core.application_entry.forms import (
    DistrictBeneficiaryEntryForm,
    InstitutionsBeneficiaryEntryForm,
    PublicBeneficiaryEntryForm,
)


class ArticlePricingModeTests(TestCase):
    def setUp(self):
        self.user = models.AppUser.objects.create_superuser(
            email="admin@example.com",
            password="testpass123",
            role=models.RoleChoices.ADMIN,
            status=models.StatusChoices.ACTIVE,
        )
        self.client.force_login(self.user)
        self.district = models.DistrictMaster.objects.create(
            district_name="Salem",
            allotted_budget=Decimal("100000.00"),
            president_name="District President",
            mobile_number="9876543210",
            application_number="D001",
            is_active=True,
        )
        self.fixed_article = models.Article.objects.create(
            article_name="Fixed Chair",
            article_name_tk="Chair",
            cost_per_unit=Decimal("1200.00"),
            allow_manual_price=False,
            item_type=models.ItemTypeChoices.ARTICLE,
            category="Furniture",
            master_category="Support",
            combo=False,
            is_active=True,
        )
        self.manual_article = models.Article.objects.create(
            article_name="Education Aid",
            article_name_tk="Education",
            cost_per_unit=Decimal("0.00"),
            allow_manual_price=True,
            item_type=models.ItemTypeChoices.AID,
            category="Aid",
            master_category="Support",
            combo=False,
            is_active=True,
        )

    def test_article_create_popup_accepts_manual_price_flag(self):
        response = self.client.post(
            reverse("ui:article-create") + "?popup=1",
            {
                "article_name": "Custom Aid",
                "article_name_tk": "Custom",
                "cost_per_unit": "0",
                "allow_manual_price": "on",
                "item_type": models.ItemTypeChoices.AID,
                "category": "Aid",
                "master_category": "Support",
                "is_active": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["article"]["allow_manual_price"])
        article = models.Article.objects.get(article_name="Custom Aid")
        self.assertTrue(article.allow_manual_price)

    def test_public_entry_form_uses_fixed_price_and_preserves_manual_price(self):
        fixed_form = PublicBeneficiaryEntryForm(
            data={
                "application_number": "P001",
                "name": "Public Beneficiary",
                "aadhar_number": "123456789012",
                "is_handicapped": models.HandicappedStatusChoices.NO,
                "gender": models.GenderChoices.MALE,
                "female_status": "",
                "address": "Public Address",
                "mobile": "9999999999",
                "article": self.fixed_article.id,
                "article_cost_per_unit": "0",
                "quantity": "2",
                "total_amount": "0",
                "notes": "Note",
                "status": models.BeneficiaryStatusChoices.DRAFT,
                "fund_request": "",
            }
        )
        self.assertTrue(fixed_form.is_valid(), fixed_form.errors)
        self.assertEqual(fixed_form.cleaned_data["article_cost_per_unit"], Decimal("1200.00"))
        self.assertEqual(fixed_form.cleaned_data["total_amount"], Decimal("2400.00"))

        manual_form = PublicBeneficiaryEntryForm(
            data={
                "application_number": "P002",
                "name": "Manual Beneficiary",
                "aadhar_number": "123456789013",
                "is_handicapped": models.HandicappedStatusChoices.NO,
                "gender": models.GenderChoices.MALE,
                "female_status": "",
                "address": "Public Address",
                "mobile": "9999999998",
                "article": self.manual_article.id,
                "article_cost_per_unit": "10000",
                "quantity": "2",
                "total_amount": "0",
                "notes": "Note",
                "status": models.BeneficiaryStatusChoices.DRAFT,
                "fund_request": "",
            }
        )
        self.assertTrue(manual_form.is_valid(), manual_form.errors)
        self.assertEqual(manual_form.cleaned_data["article_cost_per_unit"], Decimal("10000"))
        self.assertEqual(manual_form.cleaned_data["total_amount"], Decimal("20000"))

    def test_district_and_institution_forms_follow_pricing_mode(self):
        district_form = DistrictBeneficiaryEntryForm(
            data={
                "district": self.district.id,
                "application_number": "D001",
                "article": self.fixed_article.id,
                "article_cost_per_unit": "0",
                "quantity": "3",
                "total_amount": "0",
                "notes": "District note",
                "status": models.BeneficiaryStatusChoices.DRAFT,
                "fund_request": "",
            }
        )
        self.assertTrue(district_form.is_valid(), district_form.errors)
        self.assertEqual(district_form.cleaned_data["article_cost_per_unit"], Decimal("1200.00"))
        self.assertEqual(district_form.cleaned_data["total_amount"], Decimal("3600.00"))

        institution_form = InstitutionsBeneficiaryEntryForm(
            data={
                "institution_name": "SRV School",
                "institution_type": models.InstitutionTypeChoices.OTHERS,
                "application_number": "I001",
                "address": "Institution Address",
                "mobile": "8888888888",
                "article": self.manual_article.id,
                "article_cost_per_unit": "7500",
                "quantity": "2",
                "total_amount": "0",
                "notes": "Institution note",
                "status": models.BeneficiaryStatusChoices.DRAFT,
                "fund_request": "",
            }
        )
        self.assertTrue(institution_form.is_valid(), institution_form.errors)
        self.assertEqual(institution_form.cleaned_data["article_cost_per_unit"], Decimal("7500"))
        self.assertEqual(institution_form.cleaned_data["total_amount"], Decimal("15000"))

    def test_price_impact_preview_returns_counts_by_module(self):
        models.DistrictBeneficiaryEntry.objects.create(
            district=self.district,
            application_number="D100",
            article=self.fixed_article,
            article_cost_per_unit=Decimal("1200.00"),
            quantity=1,
            total_amount=Decimal("1200.00"),
            status=models.BeneficiaryStatusChoices.DRAFT,
            created_by=self.user,
        )
        models.PublicBeneficiaryEntry.objects.create(
            application_number="P100",
            name="Public Beneficiary",
            aadhar_number="123456789012",
            is_handicapped=models.HandicappedStatusChoices.NO,
            gender=models.GenderChoices.MALE,
            address="Public Address",
            mobile="9999999999",
            article=self.fixed_article,
            article_cost_per_unit=Decimal("1200.00"),
            quantity=2,
            total_amount=Decimal("2400.00"),
            status=models.BeneficiaryStatusChoices.DRAFT,
            created_by=self.user,
        )
        models.InstitutionsBeneficiaryEntry.objects.create(
            institution_name="Institution",
            institution_type=models.InstitutionTypeChoices.OTHERS,
            application_number="I100",
            address="Institution Address",
            mobile="8888888888",
            article=self.fixed_article,
            article_cost_per_unit=Decimal("1200.00"),
            quantity=3,
            total_amount=Decimal("3600.00"),
            status=models.BeneficiaryStatusChoices.DRAFT,
            created_by=self.user,
        )

        response = self.client.get(
            reverse("ui:article-price-impact", args=[self.fixed_article.id]),
            {"cost_per_unit": "1500", "allow_manual_price": "0"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["has_change"])
        self.assertEqual(payload["impact"]["district"]["count"], 1)
        self.assertEqual(payload["impact"]["public"]["count"], 1)
        self.assertEqual(payload["impact"]["institution"]["count"], 1)
        self.assertEqual(payload["recommended_scope"], "existing_and_future")

    def test_article_update_can_apply_new_price_to_existing_rows(self):
        district_entry = models.DistrictBeneficiaryEntry.objects.create(
            district=self.district,
            application_number="D100",
            article=self.fixed_article,
            article_cost_per_unit=Decimal("1200.00"),
            quantity=2,
            total_amount=Decimal("2400.00"),
            status=models.BeneficiaryStatusChoices.DRAFT,
            created_by=self.user,
        )
        public_entry = models.PublicBeneficiaryEntry.objects.create(
            application_number="P100",
            name="Public Beneficiary",
            aadhar_number="123456789012",
            is_handicapped=models.HandicappedStatusChoices.NO,
            gender=models.GenderChoices.MALE,
            address="Public Address",
            mobile="9999999999",
            article=self.fixed_article,
            article_cost_per_unit=Decimal("1200.00"),
            quantity=3,
            total_amount=Decimal("3600.00"),
            status=models.BeneficiaryStatusChoices.DRAFT,
            created_by=self.user,
        )

        response = self.client.post(
            reverse("ui:article-edit", args=[self.fixed_article.id]),
            {
                "article_name": self.fixed_article.article_name,
                "article_name_tk": self.fixed_article.article_name_tk,
                "cost_per_unit": "1500.00",
                "allow_manual_price": "",
                "item_type": self.fixed_article.item_type,
                "category": self.fixed_article.category,
                "master_category": self.fixed_article.master_category,
                "is_active": "on",
                "combo": "",
                "price_update_scope": "existing_and_future",
            },
        )

        self.assertRedirects(response, reverse("ui:article-list"))
        district_entry.refresh_from_db()
        public_entry.refresh_from_db()
        self.fixed_article.refresh_from_db()
        self.assertEqual(self.fixed_article.cost_per_unit, Decimal("1500.00"))
        self.assertEqual(district_entry.article_cost_per_unit, Decimal("1500.00"))
        self.assertEqual(district_entry.total_amount, Decimal("3000.00"))
        self.assertEqual(public_entry.article_cost_per_unit, Decimal("1500.00"))
        self.assertEqual(public_entry.total_amount, Decimal("4500.00"))

    def test_article_update_future_only_leaves_existing_manual_rows_unchanged(self):
        public_entry = models.PublicBeneficiaryEntry.objects.create(
            application_number="P200",
            name="Manual Beneficiary",
            aadhar_number="123456789099",
            is_handicapped=models.HandicappedStatusChoices.NO,
            gender=models.GenderChoices.MALE,
            address="Public Address",
            mobile="9999999988",
            article=self.manual_article,
            article_cost_per_unit=Decimal("10000.00"),
            quantity=1,
            total_amount=Decimal("10000.00"),
            status=models.BeneficiaryStatusChoices.DRAFT,
            created_by=self.user,
        )

        response = self.client.post(
            reverse("ui:article-edit", args=[self.manual_article.id]),
            {
                "article_name": self.manual_article.article_name,
                "article_name_tk": self.manual_article.article_name_tk,
                "cost_per_unit": "1200.00",
                "allow_manual_price": "on",
                "item_type": self.manual_article.item_type,
                "category": self.manual_article.category,
                "master_category": self.manual_article.master_category,
                "is_active": "on",
                "combo": "",
                "price_update_scope": "future_only",
            },
        )

        self.assertRedirects(response, reverse("ui:article-list"))
        public_entry.refresh_from_db()
        self.manual_article.refresh_from_db()
        self.assertEqual(self.manual_article.cost_per_unit, Decimal("1200.00"))
        self.assertTrue(self.manual_article.allow_manual_price)
        self.assertEqual(public_entry.article_cost_per_unit, Decimal("10000.00"))
        self.assertEqual(public_entry.total_amount, Decimal("10000.00"))
