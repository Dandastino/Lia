.PHONY: help build up down logs shell-backend shell-db restart clean build-prod up-prod down-prod init test-backend test-frontend lint

help:
	@echo "Lia Docker Commands:"
	@echo ""
	@echo "Development:"
	@echo "  make build              Build Docker images"
	@echo "  make up                 Start all services (dev)"
	@echo "  make down               Stop all services"
	@echo "  make logs               View service logs"
	@echo "  make logs-backend       View backend logs"
	@echo "  make logs-frontend      View frontend logs"
	@echo "  make logs-db            View database logs"
	@echo "  make shell-backend      Open shell in backend container"
	@echo "  make shell-db           Open psql shell in database"
	@echo "  make shell-frontend     Open shell in frontend container"
	@echo "  make restart            Restart all services"
	@echo "  make clean              Remove containers and unused images"
	@echo ""
	@echo "Production:"
	@echo "  make build-prod         Build production images"
	@echo "  make up-prod            Start production services"
	@echo "  make down-prod          Stop production services"
	@echo "  make logs-prod          View production logs"

# Development commands
build:
	docker-compose build

up:
	docker-compose up -d
	@echo "Lia is running!"
	@echo "Frontend: http://localhost:3000"
	@echo "Backend:  http://localhost:5000"

down:
	docker-compose down

logs:
	docker-compose logs -f

logs-backend:
	docker-compose logs -f backend

logs-frontend:
	docker-compose logs -f frontend

logs-db:
	docker-compose logs -f db

shell-backend:
	docker-compose exec backend bash

shell-db:
	docker-compose exec db psql -U postgres -d lia_db

shell-frontend:
	docker-compose exec frontend sh

restart:
	docker-compose restart

status:
	docker-compose ps

clean:
	docker-compose down -v
	docker system prune -f

# Production commands
build-prod:
	docker-compose -f docker-compose.production.yml build

up-prod:
	docker-compose -f docker-compose.production.yml up -d
	@echo "Production Lia is running!"

down-prod:
	docker-compose -f docker-compose.production.yml down

logs-prod:
	docker-compose -f docker-compose.production.yml logs -f

# Database commands
backup-db:
	docker-compose exec db pg_dump -U postgres -d lia_db > backup_$(shell date +%Y%m%d_%H%M%S).sql

restore-db:
	@echo "Usage: make restore-db BACKUP=backup_YYYYMMDD_HHMMSS.sql"
	ifdef BACKUP
		docker-compose exec -T db psql -U postgres -d lia_db < $(BACKUP)
	endif

# Testing (run on the host; see README "Running the checks")
test-backend:
	cd backend && python -m pytest --cov=app

test-frontend:
	cd frontend && npm test

lint:
	cd backend && ruff check .
	cd frontend && npm run lint

# Development setup
init:
	cp -n .env.example .env || true
	cp -n backend/.env.example backend/.env || true
	@echo "Environment files created. Edit .env and backend/.env (JWT_SECRET_KEY, CONNECTOR_ENCRYPTION_KEY, API keys) before 'make up'"

# Utility
version:
	@docker --version
	@docker-compose --version

prune:
	docker system prune -a --volumes

ps:
	docker-compose ps
