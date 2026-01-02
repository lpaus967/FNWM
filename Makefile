# FNWM Project Makefile
# Convenience commands for common development tasks

.PHONY: help setup install install-dev test lint format clean run-api

help:
	@echo "FNWM Development Commands"
	@echo "========================="
	@echo "make setup          - Initialize project structure"
	@echo "make install        - Install production dependencies"
	@echo "make install-dev    - Install development dependencies"
	@echo "make test           - Run all tests"
	@echo "make test-cov       - Run tests with coverage report"
	@echo "make lint           - Run linters (flake8, mypy)"
	@echo "make format         - Format code (black, isort)"
	@echo "make clean          - Remove cache and build files"
	@echo "make run-api        - Start the FastAPI development server"
	@echo "make db-up          - Start PostgreSQL via Docker"
	@echo "make db-down        - Stop PostgreSQL"

setup:
	python setup_project.py

install:
	pip install --upgrade pip
	pip install -r requirements.txt

install-dev:
	pip install --upgrade pip
	pip install -r requirements-dev.txt
	pre-commit install

test:
	pytest tests/

test-cov:
	pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

lint:
	flake8 src/ tests/
	mypy src/

format:
	black src/ tests/ scripts/
	isort src/ tests/ scripts/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .coverage htmlcov/

run-api:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

db-up:
	docker run -d \
		--name fnwm-db \
		-e POSTGRES_PASSWORD=dev_password \
		-e POSTGRES_DB=fnwm \
		-p 5432:5432 \
		timescale/timescaledb-ha:pg15

db-down:
	docker stop fnwm-db
	docker rm fnwm-db

db-shell:
	docker exec -it fnwm-db psql -U postgres -d fnwm
