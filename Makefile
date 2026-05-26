.PHONY: install test run docker-up docker-down health

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m unittest discover -s tests -v

run:
	$(PYTHON) -m uvicorn code_review_multiagent.app:app --app-dir src --reload --port 8000

docker-up:
	docker compose up --build

docker-down:
	docker compose down

health:
	curl -f http://127.0.0.1:8000/health
