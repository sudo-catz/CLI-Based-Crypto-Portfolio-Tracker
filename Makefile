.PHONY: help setup clean lint format type-check test test-cov run install-dev
.DEFAULT_GOAL := help

# Colors for terminal output
BLUE = \033[0;34m
GREEN = \033[0;32m
YELLOW = \033[1;33m
RED = \033[0;31m
NC = \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Portfolio Tracker Development Commands$(NC)"
	@echo "======================================"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "$(GREEN)%-15s$(NC) %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: ## Set up development environment
	@echo "$(BLUE)Setting up development environment...$(NC)"
	python -m venv .venv
	@echo "$(YELLOW)Activate virtual environment with: source .venv/bin/activate$(NC)"
	@echo "$(YELLOW)Then run: make install-dev$(NC)"

install-dev: ## Install development dependencies
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	pip install --upgrade pip
	pip install -r requirements.txt
	playwright install
	@echo "$(GREEN)Development environment ready!$(NC)"

clean: ## Clean up cache files and temporary directories
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	@echo "$(GREEN)Cleanup complete!$(NC)"

format: ## Format code with Black
	@echo "$(BLUE)Formatting code with Black...$(NC)"
	black --config pyproject.toml .
	@echo "$(GREEN)Code formatting complete!$(NC)"

lint: ## Run linting with flake8
	@echo "$(BLUE)Running linting with flake8...$(NC)"
	flake8 .
	@echo "$(GREEN)Linting complete!$(NC)"

type-check: ## Run type checking with mypy
	@echo "$(BLUE)Running type checking with mypy...$(NC)"
	mypy --config-file pyproject.toml .
	@echo "$(GREEN)Type checking complete!$(NC)"

test: ## Run tests with pytest
	@echo "$(BLUE)Running tests...$(NC)"
	pytest tests/ -v
	@echo "$(GREEN)Tests complete!$(NC)"

test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	pytest tests/ --cov=. --cov-report=html --cov-report=term-missing
	@echo "$(GREEN)Coverage report generated in htmlcov/$(NC)"

quality: format lint type-check ## Run all code quality checks
	@echo "$(GREEN)All quality checks complete!$(NC)"

run: ## Run the portfolio tracker
	@echo "$(BLUE)Starting Portfolio Tracker...$(NC)"
	python port2.py

check-structure: ## Verify the organized directory structure
	@echo "$(BLUE)Checking directory structure...$(NC)"
	@echo "$(GREEN)✓ Main modules:$(NC)"
	@ls -la */
	@echo "\n$(GREEN)✓ Data organization:$(NC)"
	@ls -la data/*/
	@echo "$(GREEN)Directory structure verified!$(NC)"

stats: ## Show project statistics
	@echo "$(BLUE)Project Statistics$(NC)"
	@echo "=================="
	@echo "$(GREEN)Lines of code in main modules:$(NC)"
	@find . -name "*.py" -not -path "./.venv/*" -not -path "./data/*" -not -path "./logs/*" | xargs wc -l | sort -n
	@echo "\n$(GREEN)Files by directory:$(NC)"
	@find . -type f -name "*.py" -not -path "./.venv/*" | cut -d'/' -f2 | sort | uniq -c | sort -nr

organize: ## Reorganize any loose files into proper directories
	@echo "$(BLUE)Organizing loose files...$(NC)"
	@mkdir -p data/analysis data/screenshots logs/debank
	@find . -maxdepth 1 -name "portfolio_analysis_*.json" -exec mv {} data/analysis/ \; 2>/dev/null || true
	@find . -maxdepth 1 -name "debank_error_*.png" -exec mv {} data/screenshots/ \; 2>/dev/null || true
	@find . -maxdepth 1 -name "test_*.py" -exec mv {} tests/ \; 2>/dev/null || true
	@echo "$(GREEN)Organization complete!$(NC)"

all: clean quality test ## Run complete quality pipeline
	@echo "$(GREEN)🎉 All checks passed! Ready for production! 🎉$(NC)" 