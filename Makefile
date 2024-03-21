IMAGE = natasha-bandugan
REGISTRY = cr.yandex/$(REGISTRY_ID)
REMOTE = $(REGISTRY)/$(IMAGE)

test-lint:
	pytest -vv --asyncio-mode=auto --pycodestyle --flakes main.py

test-key:
	pytest -vv --asyncio-mode=auto -s -k $(KEY) test.py

image:
	docker build -t $(IMAGE) .

push:
	docker tag $(IMAGE) $(REMOTE)
	docker push $(REGISTRY)/$(IMAGE)

deploy:
	yc serverless container revision deploy \
		--container-name default \
		--image $(REGISTRY)/$(IMAGE):latest \
		--cores 1 \
		--memory 256MB \
		--concurrency 16 \
		--execution-timeout 30s \
		--environment BOT_TOKEN=$(BOT_TOKEN) \
		--environment AWS_KEY_ID=$(AWS_KEY_ID) \
		--environment AWS_KEY=$(AWS_KEY) \
		--environment DYNAMO_ENDPOINT=$(DYNAMO_ENDPOINT) \
		--environment CHAT_ID=$(CHAT_ID) \
		--service-account-id $(SERVICE_ACCOUNT_ID) \
		--folder-name natasha-bandugan
