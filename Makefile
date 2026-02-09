# Makefile for Contract Clause Extractor Tests
# Provides convenient shortcuts for running tests

.PHONY: help test test-unit test-integration test-smoke test-cov test-fast test-all clean install-test

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo '$(BLUE)Contract Clause Extractor - Test Commands$(NC)'
	@echo ''
	@echo 'Usage:'
	@echo '  make $(GREEN)<target>$(NC)'
	@echo ''
	@echo 'Targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

install-test: ## Install test dependencies
	@echo '$(BLUE)Installing test dependencies...$(NC)'
	pip install -r tests/requirements.txt
	@echo '$(GREEN)Test dependencies installed!$(NC)'

test: ## Run all tests
	@echo '$(BLUE)Running all tests...$(NC)'
	pytest

test-unit: ## Run unit tests only (no database required)
	@echo '$(BLUE)Running unit tests...$(NC)'
	pytest -m unit -v

test-integration: ## Run integration tests (requires database)
	@echo '$(BLUE)Running integration tests...$(NC)'
	pytest -m integration -v

test-smoke: ## Run quick smoke tests
	@echo '$(BLUE)Running smoke tests...$(NC)'
	pytest -m smoke -v

test-cov: ## Run tests with coverage report
	@echo '$(BLUE)Running tests with coverage...$(NC)'
	pytest --cov=dbase --cov-report=html --cov-report=term
	@echo '$(GREEN)Coverage report generated in htmlcov/index.html$(NC)'

test-cov-term: ## Run tests with terminal coverage report
	@echo '$(BLUE)Running tests with coverage...$(NC)'
	pytest --cov=dbase --cov-report=term-missing

test-fast: ## Run tests in parallel (requires pytest-xdist)
	@echo '$(BLUE)Running tests in parallel...$(NC)'
	pytest -n auto

test-all: ## Run comprehensive test suite with coverage
	@echo '$(BLUE)Running comprehensive test suite...$(NC)'
	pytest -v --cov=dbase --cov-report=html --cov-report=term-missing
	@echo '$(GREEN)All tests complete!$(NC)'

test-verbose: ## Run tests with maximum verbosity
	@echo '$(BLUE)Running tests with verbose output...$(NC)'
	pytest -vv -s --tb=long

test-failed: ## Re-run only failed tests from last run
	@echo '$(BLUE)Re-running failed tests...$(NC)'
	pytest --lf -v

test-debug: ## Run tests with debugger on failure
	@echo '$(BLUE)Running tests with debugger...$(NC)'
	pytest --pdb

test-models: ## Run model tests only
	@echo '$(BLUE)Running model tests...$(NC)'
	pytest tests/test_models.py -v

test-repo: ## Run repository integration tests
	@echo '$(BLUE)Running repository tests...$(NC)'
	pytest tests/test_repository_integration.py -v

test-connection: ## Run connection and config tests
	@echo '$(BLUE)Running connection tests...$(NC)'
	pytest tests/test_connection_config.py -v

test-watch: ## Run tests in watch mode (requires pytest-watch)
	@echo '$(BLUE)Running tests in watch mode...$(NC)'
	@command -v ptw >/dev/null 2>&1 || { echo "$(RED)pytest-watch not installed. Run: pip install pytest-watch$(NC)"; exit 1; }
	ptw

clean: ## Remove test artifacts and cache
	@echo '$(BLUE)Cleaning test artifacts...$(NC)'
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	rm -rf htmlcov/
	rm -f .coverage
	rm -rf .eggs/
	rm -rf *.egg-info/
	@echo '$(GREEN)Clean complete!$(NC)'

check-db: ## Check if PostgreSQL is running
	@echo '$(BLUE)Checking PostgreSQL status...$(NC)'
	@if pg_isready -q; then \
		echo '$(GREEN)PostgreSQL is running$(NC)'; \
	else \
		echo '$(RED)PostgreSQL is not running. Start with: brew services start postgresql@14$(NC)'; \
		exit 1; \
	fi

lint: ## Run basic linting (requires flake8)
	@echo '$(BLUE)Running linter...$(NC)'
	@command -v flake8 >/dev/null 2>&1 || { echo "$(RED)flake8 not installed. Run: pip install flake8$(NC)"; exit 1; }
	flake8 dbase/ tests/ --max-line-length=100 --exclude=__pycache__

format: ## Format code (requires black)
	@echo '$(BLUE)Formatting code...$(NC)'
	@command -v black >/dev/null 2>&1 || { echo "$(RED)black not installed. Run: pip install black$(NC)"; exit 1; }
	black dbase/ tests/

stats: ## Show test statistics
	@echo '$(BLUE)Test Statistics$(NC)'
	@echo ''
	@echo 'Total tests:'
	@pytest --collect-only -q | tail -n 1
	@echo ''
	@echo 'Tests by marker:'
	@echo -n '  Unit tests: '
	@pytest --collect-only -q -m unit 2>/dev/null | tail -n 1 || echo '0'
	@echo -n '  Integration tests: '
	@pytest --collect-only -q -m integration 2>/dev/null | tail -n 1 || echo '0'
	@echo -n '  Smoke tests: '
	@pytest --collect-only -q -m smoke 2>/dev/null | tail -n 1 || echo '0'

ci: check-db test-smoke test-unit test-integration ## Run full CI test suite
	@echo '$(GREEN)CI test suite complete!$(NC)'

.DEFAULT_GOAL := help
