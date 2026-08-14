"""
Layer: Application
Package: application.plans.list_plans
Responsibility: Получение списка доступных тарифов.
"""
from typing import List

from application.ports.repositories import PlanRepositoryProtocol
from domain.models import Plan


class ListPlans:
    def __init__(self, plan_repository: PlanRepositoryProtocol):
        self._plan_repository = plan_repository

    def execute(self) -> List[Plan]:
        return self._plan_repository.list_active()
