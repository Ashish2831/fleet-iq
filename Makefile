.PHONY: test dist up setup seed run web gps workers

test:
	cd backend && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest tests/ -q

up:
	docker compose up -d postgres redis redpanda console mongo elasticsearch

setup:
	./scripts/dev-setup.sh

seed:
	cd backend && .venv/bin/python manage.py seed_bangalore --reset

run:
	cd backend && .venv/bin/python manage.py runserver

web:
	cd apps/web && npm run dev

gps:
	cd backend && .venv/bin/python manage.py simulate_gps --tenant acme-logistics --interval 1

workers:
	./scripts/workers.sh

dist:
	docker compose --profile dist up --build

run-dist:
	./scripts/run-dist.sh
