
# Бот для чата @natural_language_processing. Запускает голосование за бан участника чата

## Инструкции

### Как добавить @bandugan_bot в чат

Добавить бота в администраторы, забрать все права кроме "Блокировка участников", "Удалять сообщения".

## Разработка

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
pip install awscli==1.29.27
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
```

Удалить таблички.

```bash
aws dynamodb delete-table --table-name votings \
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

Логи.

```bash
yc log read default --follow --folder-name natasha-bandugan
```

Прицепить вебхук.

```bash
WEBHOOK_URL=https://${CONTAINER_ID}.containers.yandexcloud.net/
curl --url https://api.telegram.org/bot${BOT_TOKEN}/setWebhook\?url=${WEBHOOK_URL}
```

Создать окружение, установить кернел.

```bash
python -m venv .venv
source .venv/bin/activate

pip install ipykernel
python -m ipykernel install --user --name natasha-bandugan
```

Трюк чтобы загрузить окружение из `.env`.

```bash
export $(cat .env | xargs)
```

Установить зависимости для бота.

```bash
pip install \
  aiogram==2.21 \
  aiobotocore==2.3.4
```

Установить зависимости для тестов.

```bash
pip install \
  pytest-aiohttp \
  pytest-asyncio \
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
