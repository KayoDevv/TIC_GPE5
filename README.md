# Produit

Outil cybersécurité "Endpoint" B2B SaaS. Il utilise une architecture Microservices orientés événements (Kafka) avec un pattern Scatter-Gather. Objectif : Ne jamais bloquer le navigateur (100% asynchrone) et fournir un taux de faux positifs < 0.5%.

## Structure du Monorepo

Conformément aux meilleures pratiques pour les monorepos polyglottes (Python / Node.js) :
- `apps/` : Contient toutes les applications déployables et les services (Frontend, Core-Backend, Workers).
- `packages/` : Contient les bibliothèques et schémas partagés (ex. Kafka Schemas).
- `infrastructure/` : Contient les scripts et configurations d'infrastructure (Terraform, Docker, Kubernetes).
