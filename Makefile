.PHONY: run format audit test

run:
	streamlit run app.py

test:
	python -m pytest tests/ -q

format:
	black src/ app.py scripts/
	isort src/ app.py scripts/

audit:
	pip-audit -r requirements.txt