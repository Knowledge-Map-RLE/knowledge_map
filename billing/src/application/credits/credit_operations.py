"""
Layer: Application
Package: application.credits
Responsibility: Операции с кредитами пользователя.
"""
import uuid

from application.ports.repositories import CreditRepositoryProtocol
from domain.exceptions import NotEnoughCreditsError
from domain.models import CreditAccount, CreditTransaction
from domain.models.credit import CreditTransactionType


class CreditOperations:
    """Единый сервис операций с кредитами (начисление/списание/баланс/история)."""

    def __init__(self, credit_repository: CreditRepositoryProtocol):
        self._credit_repository = credit_repository

    def get_balance(self, *, user_id: str) -> int:
        return self._credit_repository.get_balance(user_id)

    def get_account(self, *, user_id: str) -> CreditAccount:
        return self._credit_repository.get_or_create_account(user_id)

    def grant(
        self,
        *,
        user_id: str,
        amount: int,
        reference_id: str | None = None,
        description: str | None = None,
    ) -> CreditAccount:
        if amount <= 0:
            raise ValueError("Grant amount must be positive")
        account = self._credit_repository.get_or_create_account(user_id)
        return self._credit_repository.apply_transaction(
            CreditTransaction(
                uid=str(uuid.uuid4()),
                account_uid=account.uid,
                user_id=user_id,
                amount=amount,
                type=CreditTransactionType.MANUAL,
                reference_id=reference_id,
                description=description,
            )
        )

    def deduct(
        self,
        *,
        user_id: str,
        amount: int,
        reference_id: str | None = None,
        description: str | None = None,
    ) -> CreditAccount:
        if amount <= 0:
            raise ValueError("Deduct amount must be positive")
        account = self._credit_repository.get_or_create_account(user_id)
        if account.balance < amount:
            raise NotEnoughCreditsError(
                f"Insufficient credits: {account.balance} available, {amount} required"
            )
        return self._credit_repository.apply_transaction(
            CreditTransaction(
                uid=str(uuid.uuid4()),
                account_uid=account.uid,
                user_id=user_id,
                amount=-amount,
                type=CreditTransactionType.AI_USAGE,
                reference_id=reference_id,
                description=description,
            )
        )

    def deduct_idempotent(
        self,
        *,
        user_id: str,
        amount: int,
        reference_id: str,
        description: str | None = None,
    ) -> CreditAccount:
        """Списывает кредиты за AI-запрос ровно один раз.

        ``reference_id`` — id ответа провайдера. Если транзакция с таким
        reference_id уже существует — списание повторно не выполняется
        (идемпотентность: повторная доставка из api после таймаута безопасна).
        """
        if not reference_id:
            raise ValueError("reference_id is required for idempotent deduct")
        existing = self._credit_repository.get_transaction_by_reference_id(reference_id)
        if existing is not None:
            account = self._credit_repository.get_account(user_id)
            return account or self._credit_repository.get_or_create_account(user_id)
        return self.deduct(
            user_id=user_id,
            amount=amount,
            reference_id=reference_id,
            description=description,
        )

    def list_transactions(self, *, user_id: str, limit: int = 50):
        return self._credit_repository.list_transactions(user_id, limit=limit)
