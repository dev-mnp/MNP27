from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import models
from core import services


class FundRequestListRegressionTests(TestCase):
    def setUp(self):
        self.user = models.AppUser.objects.create_superuser(
            email="admin@example.com",
            password="testpass123",
            role=models.RoleChoices.ADMIN,
            status=models.StatusChoices.ACTIVE,
        )
        self.client.force_login(self.user)

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

    def test_submitted_list_shows_each_fund_request_once_with_multiple_recipients(self):
        fr5 = self._create_fund_request(number="FR-005", created_at=timezone.now())
        self._add_recipients(fr5, 4, details_prefix="Medical detail")

        fr6 = self._create_fund_request(number="FR-006", created_at=timezone.now() + timezone.timedelta(minutes=5), total_amount=44100)
        models.FundRequestArticle.objects.create(
            fund_request=fr6,
            article=models.Article.objects.create(
                article_name="Wheelchair",
                cost_per_unit=44100,
                item_type=models.ItemTypeChoices.ARTICLE,
                combo=False,
                is_active=True,
            ),
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
