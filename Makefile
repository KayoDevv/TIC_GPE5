.PHONY: help up down test lint format

help:
	@echo "Commandes disponibles :"
	@echo "  make up      - Démarre l'environnement de développement local (Kafka, Redis, MinIO)"
	@echo "  make down    - Arrête l'environnement de développement local"
	@echo "  make test    - Lance tous les tests (Frontend et Backend)"
	@echo "  make lint    - Vérifie le formatage du code"
	@echo "  make format  - Formate le code (--fix)"

up:
	docker-compose up -d

down:
	docker-compose down

test:
	# Ajoutez ici les commandes pour lancer vos tests (ex: pytest, playwright)
	@echo "Exécution des tests..."

lint:
	# Ajoutez ici les commandes de linting (ex: ruff check ., npm run lint)
	@echo "Vérification du code..."

format:
	# Ajoutez ici les commandes de formatage (ex: ruff format ., npm run format)
	@echo "Formatage du code..."
