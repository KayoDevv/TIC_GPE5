# Verdict Layer : Verdict (Le Moteur d'Agrégation)

**Tech :** Python, Redis (pour l'état).

**Code Guidelines :** TDD (pytest-asyncio). Implémentation du pattern Saga.

**Contexte Métier :** "Le Moteur d'Agrégation". Consolide les réponses asynchrones et applique la matrice de décision.

**Responsabilité :** Gérer les timeouts globaux. Si le Sandbox Layer ne répond pas au bout de 125s, émettre un statut "Suspect par défaut".

**Événements Kafka (Consommés/Produits) :**
- **Consomme :** `ml_layer.result`, `sandbox_layer.result`, `llm_layer.result`.
- **Produit :** Événement métier de verdict final `verdict.result` à destination du Backend/WebSockets.

## Specifications Techniques
- **Gestion de l'État (State Management) :** Utilisation de Redis en mode clé-valeur avec Time-To-Live (TTL) pour stocker temporairement les retours asynchrones de chaque Layer via la clé commune `job_id`.
- **Pattern Saga & Orchestration :** 
  1. Dès réception d'un événement intermédiaire (`ml_layer.result`, etc.), le microservice met à jour l'état partiel dans Redis.
  2. Implémentation d'une fonction de vérification (Polling asynchrone ou Pub/Sub) pour déterminer si l'intégralité du cycle de vie du job est achevée.
  3. Gestion stricte du **Timeout Sandbox (125s)** : Si le Sandbox ne répond pas dans ce délai, le Verdict Engine doit forcer l'état et clôre le dossier.
- **Matrice de Décision :**
  - Si `ml_layer` attribue un score > 90 -> Verdict `blocked` immédiat (le reste est ignoré ou traité en mode "background" pour logs).
  - Si `llm_layer` conclut à une anomalie (`is_malicious: true`) -> Verdict `blocked`.
  - Si timeout Sandbox -> Statut `warning` ou `blocked` par défaut, selon la configuration de tolérance au risque du tenant.
- **Sortie :** Formatage et émission du document consolidé vers le topic `verdict.result` pour consommation Frontend.
