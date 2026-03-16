# Shared Python Core

Ce package contient les ressources partagées par tous les microservices Python (Core Backend et Workers).

## Contenu

- `logging/` : Configuration structurée des logs.
- `kafka/` : Wrappers pour les producteurs et consommateurs Kafka.
- `models/` : Modèles Pydantic partagés (événements Kafka, requêtes/réponses).
- `config/` : Gestion unifiée de la configuration (variables d'environnement).
