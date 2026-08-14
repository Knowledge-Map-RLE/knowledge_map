"""
Layer: Application
Package: application.payments.list_payments
Responsibility: История платежей пользователя.
"""
from typing import List

from application.ports.repositories import PaymentRepositoryProtocol
from domain.models import Payment


class ListPayments:
    def __init__(self, payment_repository: PaymentRepositoryProtocol):
        self._payment_repository = payment_repository

    def execute(self, *, user_id: str, limit: int = 50) -> List[Payment]:
        return self._payment_repository.list_by_user(user_id, limit=limit)
