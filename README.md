
# Бот для чата @natural_language_processing. Запускает голосование за бан участника чата

## Инструкции

### Как добавить @bandugan_bot в чат

Добавить бота в администраторы, забрать все права кроме "Блокировка участников", "Удалять сообщения".

## Разработка

Создать Virtualenv.

```bash
python -m venv .venv
direnv allow .
```

Создать директорию в YC.

```bash
yc resource-manager folder create --name natasha-bandugan
```

Создать сервисный аккаунт в YC. Записать `id` в `.env`.

```bash
yc iam service-accounts create natasha-bandugan --folder-name natasha-bandugan

id: {SERVICE_ACCOUNT_ID}
```

Сгенерить ключи для DynamoDB, добавить их в `.env`.

```bash
yc iam access-key create \
  --service-account-name natasha-bandugan \
  --folder-name natasha-bandugan

key_id: {AWS_KEY_ID}
secret: {AWS_KEY}
```

Назначить роли, сервисный аккаунт может только писать и читать YDB.

```bash
for role in ydb.viewer ydb.editor
do
  yc resource-manager folder add-access-binding natasha-bandugan \
    --role $role \
    --service-account-name natasha-bandugan \
    --folder-name natasha-bandugan \
    --async
done
```

Создать базу YDB. Записать эндпоинт для DynamoDB в `.env`.

```bash
yc ydb database create default --serverless --folder-name natasha-bandugan

document_api_endpoint: {DYNAMO_ENDPOINT}
```

Установить, настроить `aws`.

```bash
aws configure --profile natasha-bandugan

{AWS_KEY_ID}
{AWS_KEY}
ru-central1
```

Создать табличку.

```bash
aws dynamodb create-table \
  --table-name votings \
  --attribute-definitions \
    AttributeName=poll_id,AttributeType=S \
  --key-schema \
    AttributeName=poll_id,KeyType=HASH \
  --endpoint $DYNAMO_ENDPOINT \
  --profile natasha-bandugan

aws dynamodb create-table \
  --table-name user_stats \
  --attribute-definitions \
    AttributeName=key,AttributeType=S \
  --key-schema \
    AttributeName=key,KeyType=HASH \
  --endpoint $DYNAMO_ENDPOINT \
  --profile natasha-bandugan
```

Удалить таблички.

```bash
aws dynamodb delete-table --table-name votings \
  --endpoint $DYNAMO_ENDPOINT \
  --profile natasha-bandugan

aws dynamodb delete-table --table-name user_stats \
  --endpoint $DYNAMO_ENDPOINT \
  --profile natasha-bandugan
```

Список таблиц.

```bash
aws dynamodb list-tables \
  --endpoint $DYNAMO_ENDPOINT \
  --profile natasha-bandugan
```

Прочитать табличку.

```bash
aws dynamodb scan \
  --table-name votings \
  --endpoint $DYNAMO_ENDPOINT \
  --profile natasha-bandugan
```

Создать реестр для контейнера в YC. Записать `id` в `.env`.

```bash
yc container registry create default --folder-name natasha-bandugan

id: {REGISTRY_ID}
```

Дать права сервисному аккаунту читать из реестра. Интеграция с YC Serverless Container.

```bash
yc container registry add-access-binding default \
  --role container-registry.images.puller \
  --service-account-name natasha-bandugan \
  --folder-name natasha-bandugan
```

Создать Serverless Container. Записать `id` в `.env`.

```bash
yc serverless container create --name default --folder-name natasha-bandugan

id: {CONTAINER_ID}
```

Разрешить без токена. Телеграм дергает вебхук.

```bash
yc serverless container allow-unauthenticated-invoke default \
  --folder-name natasha-bandugan
```

Мониторить логи.

```bash
yc log read default \
  --filter 'json_payload.source = "user"' \
  --follow \
  --folder-name natasha-bandugan
```

Последние 1000 записей.

```bash
yc log read default \
  --filter 'json_payload.source = "user"' \
  --limit 1000 \
  --since 2020-01-01T00:00:00Z \
  --until 2030-01-01T00:00:00Z \
  --folder-name natasha-bandugan
```

Прицепить вебхук.

```bash
WEBHOOK_URL=https://${CONTAINER_ID}.containers.yandexcloud.net/
curl --url https://api.telegram.org/bot${BOT_TOKEN}/setWebhook\?url=${WEBHOOK_URL}
```

Установить зависимости для бота.

```bash
pip install \
  aiogram==2.21 \
  aiobotocore==2.3.4 \
  aiohttp==3.8.6
```

Установить зависимости для тестов.

```bash
pip install \
  pytest==8.1.1 \
  pytest-aiohttp==1.0.5 \
  pytest-asyncio==0.23.6 \
  pytest-flakes==4.0.5 \
  pytest-pycodestyle==2.3.1
```

Прогнать линтер, тесты.

```bash
make test-lint test-key KEY=test
```

Собрать образ, загрузить его в реестр, задеплоить

```bash
make image push deploy
```
