"""
Layer: Domain
Package: domain.rules
Responsibility: Чистые бизнес-правила (без внешних зависимостей).

Внимание: не реэкспортируйте модули правил здесь — subscription_rules
и payment_state импортируют domain.models, что создаёт цикл при
инициализации пакета. Используйте полные пути: domain.rules.time и т.д.
"""
