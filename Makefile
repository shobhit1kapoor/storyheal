SHELL := /bin/bash
.DEFAULT_GOAL := help
ENV_FILE ?= .env
COMPOSE := docker compose --env-file $(ENV_FILE)

.PHONY: help up up-local-ai down logs ps migrate test backup restore

help:
	@echo "StoryHeal"
	@echo "  make up             Start the production-shaped stack"
	@echo "  make up-local-ai    Start with Ollama Qwen models"
	@echo "  make migrate        Apply API, AI, and RAG migrations"
	@echo "  make test           Run backend test suites"
	@echo "  make backup         Write a timestamped PostgreSQL backup"

up:
	@$(COMPOSE) up -d --build

up-local-ai:
	@$(COMPOSE) --profile local-ai up -d --build

down:
	@$(COMPOSE) --profile local-ai down --remove-orphans

logs:
	@$(COMPOSE) logs -f $(SERVICE)

ps:
	@$(COMPOSE) ps

migrate:
	@$(COMPOSE) run --rm storyheal-api alembic upgrade head
	@$(COMPOSE) run --rm storyheal-ai alembic upgrade head
	@$(COMPOSE) run --rm storyheal-rag alembic upgrade head

test:
	@$(COMPOSE) run --rm storyheal-api pytest -q
	@$(COMPOSE) run --rm storyheal-ai pytest -q
	@$(COMPOSE) run --rm storyheal-rag pytest -q

backup:
	@mkdir -p backups
	@$(COMPOSE) exec -T postgres pg_dump -U $${POSTGRES_USER:-storyheal} -d $${POSTGRES_DB:-storyheal} -Fc > backups/storyheal-$$(date +%Y%m%d-%H%M%S).dump

restore:
	@test -n "$(FILE)" || (echo "Usage: make restore FILE=backups/file.dump" && exit 1)
	@$(COMPOSE) exec -T postgres pg_restore --clean --if-exists -U $${POSTGRES_USER:-storyheal} -d $${POSTGRES_DB:-storyheal} < $(FILE)
