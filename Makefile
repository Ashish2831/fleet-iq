.PHONY: test dist up

test:
	cd backend && .venv/bin/python -m pytest tests/ -q

up:
	docker compose up -d postgres redis redpanda mongo elasticsearch

dist:
	docker compose --profile dist up --build

run-dist:
	./scripts/run-dist.sh
