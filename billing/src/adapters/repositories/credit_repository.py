"""
Layer: Interface Adapters
Package: adapters.repositories.credit_repository
Responsibility: Репозиторий кредитов (CreditAccount/CreditTransaction) на neomodel.

Атомарность: изменение баланса и запись транзакции выполняются одним Cypher-запросом
с условием ``a.balance + $amount >= 0``. Параллельные списания не могут увести
баланс ниже нуля — лимит пакета не нарушается даже при конкурентных запросах.
"""
import uuid
from typing import List, Optional

from neomodel import db

from domain.exceptions import NotEnoughCreditsError
from domain.models import CreditAccount, CreditTransaction
from infrastructure.neo4j_models import CreditAccountNode, CreditTransactionNode


class CreditRepository:
    def get_or_create_account(self, user_id: str) -> CreditAccount:
        node = CreditAccountNode.nodes.get_or_none(user_id=user_id)
        if node is None:
            node = CreditAccountNode(uid=str(uuid.uuid4()), user_id=user_id, balance=0)
            node.save()
        return self._to_domain(node)

    def get_account(self, user_id: str) -> Optional[CreditAccount]:
        node = CreditAccountNode.nodes.get_or_none(user_id=user_id)
        return self._to_domain(node) if node else None

    def get_balance(self, user_id: str) -> int:
        node = CreditAccountNode.nodes.get_or_none(user_id=user_id)
        return node.balance if node else 0

    def apply_transaction(self, transaction: CreditTransaction) -> CreditAccount:
        """Атомарно применяет транзакцию (grant/deduct) к балансу аккаунта.

        Один Cypher-запрос: условное обновление баланса + создание записи
        транзакции. Если ``amount`` отрицательный (списание) и баланса не
        хватает — WHERE не совпадает, запрос не возвращает строк, и кидается
        ``NotEnoughCreditsError``. Гонки исключены: проверка и запись в одной
        атомарной операции.
        """
        params = {
            "account_uid": transaction.account_uid,
            "tx_uid": transaction.uid,
            "user_id": transaction.user_id,
            "amount": transaction.amount,
            "type": transaction.type,
            "reference_id": transaction.reference_id or None,
            "description": transaction.description,
            "created_at": transaction.created_at,
        }
        query = """
        MATCH (a:CreditAccount {uid: $account_uid})
        WHERE a.balance + $amount >= 0
        SET a.balance = a.balance + $amount
        CREATE (t:CreditTransaction {
            uid: $tx_uid,
            account_uid: $account_uid,
            user_id: $user_id,
            amount: $amount,
            type: $type,
            reference_id: $reference_id,
            description: $description,
            created_at: $created_at
        })
        RETURN a.balance AS balance
        """
        results, _meta = db.cypher_query(query, params=params)
        if not results:
            raise NotEnoughCreditsError(
                f"Insufficient credits: not enough for amount {transaction.amount}"
            )
        account = CreditAccountNode.nodes.get(uid=transaction.account_uid)
        return self._to_domain(account)

    def get_transaction_by_reference_id(self, reference_id: str) -> Optional[CreditTransaction]:
        if not reference_id:
            return None
        node = CreditTransactionNode.nodes.get_or_none(reference_id=reference_id)
        if node is None:
            return None
        return self._to_transaction_domain(node)

    def list_transactions(self, user_id: str, limit: int = 50) -> List[CreditTransaction]:
        nodes = (
            CreditTransactionNode.nodes.filter(user_id=user_id)
            .order_by("-created_at")[:limit]
        )
        return [self._to_transaction_domain(node) for node in nodes]

    @staticmethod
    def _to_domain(node: CreditAccountNode) -> CreditAccount:
        return CreditAccount(
            uid=node.uid,
            user_id=node.user_id,
            balance=node.balance,
            created_at=node.created_at,
        )

    @staticmethod
    def _to_transaction_domain(node: CreditTransactionNode) -> CreditTransaction:
        return CreditTransaction(
            uid=node.uid,
            account_uid=node.account_uid,
            user_id=node.user_id,
            amount=node.amount,
            type=node.type,
            reference_id=node.reference_id,
            description=node.description,
            created_at=node.created_at,
        )
