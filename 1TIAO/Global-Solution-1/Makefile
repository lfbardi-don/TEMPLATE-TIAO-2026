.PHONY: up down migrate api psql logs

up:        ## sobe o Postgres (Docker)
	docker compose up -d db

down:      ## derruba os containers
	docker compose down

migrate:   ## aplica db/schema.sql (idempotente)
	python scripts/migrate.py

api:       ## roda a API em http://localhost:8000
	uvicorn ephemnous.infra.api:app --reload --port 8000

dash:      ## roda o dashboard em http://localhost:8501
	streamlit run dashboard/app.py

sim:       ## popula dados: 60 passos do no sim-1
	python scripts/run_node_sim.py 60 sim-1 3

live:      ## sim ao vivo: 1 tick/seg por ~15 min (para gravar o dashboard reagindo)
	python scripts/run_node_sim.py 900 sim-1 3 1

psql:      ## abre o psql no banco
	docker compose exec db psql -U ephemnous -d ephemnous

logs:      ## logs do Postgres
	docker compose logs -f db
