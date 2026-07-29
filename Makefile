.PHONY: run format audit

run:
	streamlit run app.py

format:
	black src/ app.py scripts/
	isort src/ app.py scripts/

audit:
	pip-audit -r requirements.txt