# Core Backend

**Tech :** Python (FastAPI).

**Code Guidelines :** TDD, tests unitaires via pytest/pytest-asyncio. Linting strict avec Ruff / MyPy.

**Contexte Métier :** Point d'entrée sécurisé. Authentification via JWT tokens émis par SSO.

**Responsabilité :** Valider la taille des fichiers (max 35 Mo), uploader de manière sécurisée vers S3/MinIO, et initier l'analyse asynchrone.

**Événements Kafka (Consommés/Produits) :**
- **Produit :** `file.requested` (Contient URL S3, contexte email, empreinte).
