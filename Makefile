.PHONY: install test lint run-guard run-mcp deploy clean

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest tests/ -v

lint:
	.venv/bin/ruff check src/ tests/
	.venv/bin/ruff format --check src/ tests/

run-guard:
	.venv/bin/python -m src.api.server

run-mcp:
	.venv/bin/python -m gcode.mcp.server

deploy:
	sudo bash deploy/setup.sh

clean:
	rm -rf __pycache__ src/**/__pycache__ .pytest_cache *.egg-info
	rm -rf .venv
