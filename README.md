
# Бот для чата @natural_language_processing. Запускает голосование за бан участника чата

## Инструкции

### Как добавить @bandugan_bot в чат

Добавить бота в администраторы, забрать все права кроме "Блокировка участников", "Удалять сообщения".

## Разработка

Создать директорию в YC.

```bash
yc resource-manager folder create --name natasha-bandugan-bot
```

Создать сервисный аккаунт в YC. Записать `id` в `.env`.

```bash
yc iam service-accounts create natasha-bandugan-bot --folder-name natasha-bandugan-bot

id: {SERVICE_ACCOUNT_ID}
```

Сгенерить ключи для DynamoDB, добавить их в `.env`.

```bash
yc iam access-key create \
  --service-account-name natasha-bandugan-bot \
  --folder-name natasha-bandugan-bot

key_id: {AWS_KEY_ID}
secret: {AWS_KEY}
```

Назначить роли, сервисный аккаунт может только писать и читать YDB.

```bash
for role in ydb.viewer ydb.editor
do
  yc resource-manager folder add-access-binding natasha-bandugan-bot \
    --role $role \
    --service-account-name natasha-bandugan-bot \
    --folder-name natasha-bandugan-bot \
    --async
done
```

Создать базу YDB. Записать эндпоинт для DynamoDB в `.env`.

```bash
yc ydb database create default --serverless --folder-name natasha-bandugan-bot

document_api_endpoint: {DYNAMO_ENDPOINT}
```

Установить, настроить `aws`.

```bash
pip install awscli
aws configure --profile natasha-bandugan-bot

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
  --profile natasha-bandugan-bot
```

Удалить таблички.

```bash
aws dynamodb delete-table --table-name votings \
  --endpoint $DYNAMO_ENDPOINT \
  --profile natasha-bandugan-bot
```

Список таблиц.

```bash
aws dynamodb list-tables \
  --endpoint $DYNAMO_ENDPOINT \
  --profile natasha-bandugan-bot
```

Прочитать табличку.

```bash
aws dynamodb scan \
  --table-name votings \
  --endpoint $DYNAMO_ENDPOINT \
  --profile natasha-bandugan-bot
```

Создать реестр для контейнера в YC. Записать `id` в `.env`.

```bash
yc container registry create default --folder-name natasha-bandugan-bot

id: {REGISTRY_ID}
```

Дать права сервисному аккаунту читать из реестра. Интеграция с YC Serverless Container.

```bash
yc container registry add-access-binding default \
  --role container-registry.images.puller \
  --service-account-name natasha-bandugan-bot \
  --folder-name natasha-bandugan-bot
```

Создать Serverless Container. Записать `id` в `.env`.

```bash
yc serverless container create --name default --folder-name natasha-bandugan-bot

id: {CONTAINER_ID}
```

Разрешить без токена. Телеграм дергает вебхук.

```bash
yc serverless container allow-unauthenticated-invoke default \
  --folder-name natasha-bandugan-bot
```

Логи.

```bash
yc log read default --follow --folder-name natasha-bandugan-bot
```

Прицепить вебхук.

```bash
WEBHOOK_URL=https://${CONTAINER_ID}.containers.yandexcloud.net/
curl --url https://api.telegram.org/bot${BOT_TOKEN}/setWebhook\?url=${WEBHOOK_URL}
```

Трюк чтобы загрузить окружение из `.env`.

```bash
export $(cat .env | xargs)
```

Установить зависимости для тестов.

```bash
pip install \
  pytest-aiohttp \
  pytest-asyncio \
  pytest-cov \
  pytest-flakes \
  pytest-pycodestyle
```

Прогнать линтер, тесты.

```bash
make test-lint test-key KEY=test
```

Собрать образ, загрузить его в реестр, задеплоить

```bash
make image push deploy
```
