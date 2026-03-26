from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import models


class PurchaseOrderModuleTests(TestCase):
    def setUp(self):
        self.user = models.AppUser.objects.create_superuser(
            email="admin@example.com",
            password="testpass123",
            role=models.RoleChoices.ADMIN,
            status=models.StatusChoices.ACTIVE,
        )
        self.client.force_login(self.user)

        self.article = models.Article.objects.create(
            article_name="Water Can",
            cost_per_unit=250,
            item_type=models.ItemTypeChoices.ARTICLE,
            combo=False,
            is_active=True,
        )

    def test_purchase_order_list_shows_article_requests_only(self):
        purchase_order = models.PurchaseOrder.objects.create(
            status=models.FundRequestStatusChoices.DRAFT,
            vendor_name="Vendor A",
            vendor_address="Street 1",
            vendor_city="Chennai",
            vendor_state="Tamil Nadu",
            vendor_pincode="600001",
            created_by=self.user,
        )
        models.PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            article=self.article,
            article_name=self.article.article_name,
            supplier_article_name="Vendor Water Can",
            description="Blue 20L water can",
            quantity=2,
            unit_price=250,
            total_value=500,
        )

        response = self.client.get(reverse("ui:purchase-order-list"))

        self.assertEqual(response.status_code, 200)
        ids = [purchase_order.id for purchase_order in response.context["purchase_orders"]]
        self.assertEqual(ids, [purchase_order.id])

    def test_purchase_order_form_shows_comments_field(self):
        response = self.client.get(reverse("ui:purchase-order-create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Comments or Special Instructions")
        self.assertContains(response, 'name="comments"', html=False)
        self.assertContains(response, "Purchase order issued with reference to:")

    def test_purchase_order_pdf_assigns_number_and_returns_pdf(self):
        purchase_order = models.PurchaseOrder.objects.create(
            status=models.FundRequestStatusChoices.SUBMITTED,
            vendor_name="Vendor A",
            vendor_address="Street 1",
            vendor_city="Chennai",
            vendor_state="Tamil Nadu",
            vendor_pincode="600001",
            created_by=self.user,
        )
        models.PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            article=self.article,
            article_name=self.article.article_name,
            supplier_article_name="Vendor Water Can",
            description="Blue 20L water can",
            quantity=2,
            unit_price=250,
            total_value=500,
        )

        response = self.client.get(reverse("ui:purchase-order-pdf", args=[purchase_order.id]))

        purchase_order.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(purchase_order.purchase_order_number.startswith("MASM/MNP"))
        self.assertEqual(len(purchase_order.purchase_order_number.replace("MASM/MNP", "")), 5)
        self.assertTrue(purchase_order.purchase_order_number.endswith(timezone.localdate().strftime("%y")))

    def test_next_purchase_order_number_uses_highest_current_year_sequence(self):
        year_suffix = timezone.localdate().strftime("%y")
        models.PurchaseOrder.objects.create(
            purchase_order_number=f"MASM/MNP001{year_suffix}",
            status=models.FundRequestStatusChoices.SUBMITTED,
            vendor_name="Vendor A",
            vendor_address="Street 1",
            vendor_city="Chennai",
            vendor_state="Tamil Nadu",
            vendor_pincode="600001",
            created_by=self.user,
        )
        models.PurchaseOrder.objects.create(
            purchase_order_number=f"MASM/MNP022{year_suffix}",
            status=models.FundRequestStatusChoices.SUBMITTED,
            vendor_name="Vendor B",
            vendor_address="Street 2",
            vendor_city="Chennai",
            vendor_state="Tamil Nadu",
            vendor_pincode="600002",
            created_by=self.user,
        )
        models.PurchaseOrder.objects.create(
            purchase_order_number="MASM/MNP99925",
            status=models.FundRequestStatusChoices.SUBMITTED,
            vendor_name="Vendor Old",
            vendor_address="Street 3",
            vendor_city="Chennai",
            vendor_state="Tamil Nadu",
            vendor_pincode="600003",
            created_by=self.user,
        )

        from core import services

        self.assertEqual(services.next_purchase_order_number(), f"MASM/MNP023{year_suffix}")

    def test_purchase_order_list_expanded_view_contains_details_and_items(self):
        purchase_order = models.PurchaseOrder.objects.create(
            purchase_order_number=f"MASM/MNP001{timezone.localdate().strftime('%y')}",
            status=models.FundRequestStatusChoices.SUBMITTED,
            vendor_name="Vendor A",
            vendor_address="Street 1",
            vendor_city="Chennai",
            vendor_state="Tamil Nadu",
            vendor_pincode="600001",
            comments="Delivery Period - Within a Week.",
            created_by=self.user,
        )
        models.PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            article=self.article,
            article_name=self.article.article_name,
            supplier_article_name="Vendor Water Can",
            description="Blue 20L water can",
            quantity=2,
            unit_price=250,
            total_value=500,
        )

        response = self.client.get(reverse("ui:purchase-order-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vendor Address")
        self.assertContains(response, "Supplier Article Name")
        self.assertContains(response, "Blue 20L water can")
        self.assertContains(response, "Delivery Period - Within a Week.")
