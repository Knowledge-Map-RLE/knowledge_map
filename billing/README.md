# Billing (Knowledge Map)

Микросервис подписок, платежей (ЮKassa) и кредитов для Knowledge Map.

## Стек

- Python 3.12, FastAPI 0.104.1, uvicorn 0.24.0
- Neo4j + neomodel 5.3.1 (Persist)
- ЮKassa API v3 (Basic auth, Idempotence-Key)
- gRPC-клиент к микросервису auth (проверка токена)
- Poetry (зависимости), pytest (тесты)

## Архитектура

Чистая архитектура по слоям:

```
src/
├── config.py                 # Настройки (env + .env)
├── domain/                   # Доменные модели, правила, исключения
│   ├── models/               # Plan, Subscription, Payment, PaymentEvent, Refund, Credit
│   └── rules/                # money, payment_state, subscription_rules, time
├── application/              # Use cases
│   ├── ports/                # Repositories, PaymentProviderProtocol
│   ├── checkout/             # CreateCheckout
│   ├── subscriptions/        # Activate/Cancel/Get subscription
│   ├── payments/             # ListPayments, RefundPayment
│   ├── webhooks/             # ProcessProviderEvent (идемпотентная обработка)
│   ├── credits/              # CreditOperations
│   ├── plans/                # ListPlans
│   └── access/               # CheckAccess
├── adapters/                 # Репозитории (neomodel), ЮKassa-гейтвей
├── infrastructure/           # Neo4j-модели, auth gRPC-клиент, сид тарифов, сверка
└── web/                      # FastAPI app, роутеры, зависимости, обработчики ошибок
```

## Запуск локально

1. Скопируйте `.env.example` в `.env` и заполните `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY`.
2. Запустите Neo4j (по умолчанию `bolt://localhost:7687`, логин `neo4j`, пароль `password`).
3. Запустите микросервис auth (порт 50057).
4. `./start.ps1` — установка зависимостей, генерация прото, запуск на `http://localhost:50058`.

Swagger: `http://localhost:50058/docs`. Health: `http://localhost:50058/billing/health`.

## Тарифы (сид при старте)

| Код  | Цена      | Кредитов/мес |
|------|-----------|--------------|
| FREE | 0 ₽       | 100          |
| PRO  | 1 500 ₽   | 10 000       |
| MAX  | 20 000 ₽  | 200 000      |

## Эндпоинты

- `GET  /billing/health` — проверка живости
- `GET  /billing/plans` — список тарифов
- `POST /billing/checkout` — создание платежа (`{"plan_code": "PRO"}`)
- `GET  /billing/subscription` — текущая подписка + баланс кредитов
- `POST /billing/subscription/cancel` — отмена с конца периода
- `GET  /billing/payments` — история платежей
- `POST /billing/payments/refund` — возврат средств
- `GET  /billing/credits`, `GET /billing/credits/transactions` — кредиты
- `GET  /billing/access?required_plan=PRO` — проверка доступа
- `POST /billing/webhooks/yookassa` — вебхуки ЮKassa

## Безопасность вебхуков

ЮKassa не подписывает уведомления. Безопасность обеспечивается:

1. Идемпотентностью: `external_event_id = "{provider_payment_id}:{event_type}"`
   с уникальным индексом в Neo4j (повторная доставка и конкурентные дубли не
   приводят к повторному начислению).
2. Перепроверкой статуса/суммы/валюты через `GET /v3/payments/{id}`.
3. Фоновой сверкой незавершённых платежей (`RECONCILIATION_INTERVAL_SECONDS`, по умолчанию 300 с).

## Тесты

```
poetry run pytest
```
