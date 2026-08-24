.PHONY: demo-real

demo-real:
	docker compose up -d --wait postgres
	uv run python scripts/demo_real.py
