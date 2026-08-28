.PHONY: run test format audit docker-up docker-down docker-build

run:
	streamlit run app.py

test:
	python -m pytest tests/ -q

format:
	black src/ app.py scripts/
	isort src/ app.py scripts/

audit:
	pip-audit -r requirements.txt

docker-build:
	docker compose build

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down