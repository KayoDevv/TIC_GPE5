# LLM Layer : LLM (L'Analyste Sémantique)

**Tech :** Python, Modèle LLM spécialisé (ex: Llama 3 8B auto-hébergé via vLLM ou gRPC).

**Code Guidelines :** TDD (pytest-asyncio). SLA de traitement : 3 à 5 secondes.

**Contexte Métier :** "L'Analyste Sémantique". Corrèle le contexte initial de l'email avec les résultats techniques pour déterminer l'intention réelle.

**Responsabilité :** Traduire les logs techniques en un résumé humain clair pour l'utilisateur non-technique.

**Événements Kafka (Consommés/Produits) :**
- **Consomme :** `sandbox_layer.result` (Doit inclure le rapport technique ET le contexte du corps de l'email).
- **Produit :** `llm_layer.result` (Décision binaire Malveillant/Sain + String explicatif).

## Specifications Techniques
- **Moteur LLM :** Inférence locale via `vLLM` (pour optimiser l'utilisation VRAM) ou serveur gRPC distant. Le modèle recommandé est de type Llama-3-8B-Instruct ou équivalent, capable d'être fine-tuné sur la cybersécurité.
- **Prompt Engineering :** Template strict. Le prompt injecte le contexte métier (expéditeur, sujet, corps de l'email) et le lie au rapport JSON d'IOC (généré par le Sandbox Layer).
- **Traitement Asynchrone :** 
  1. Parsing et agrégation des données techniques du rapport Sandbox.
  2. Appel asynchrone au modèle LLM en fixant une température très basse (ex: `0.1` à `0.3`) pour éviter les hallucinations.
- **Sortie :** Décision binaire claire sous forme de booléen (`is_malicious`) et génération d'un texte d'explication (`explanation_text`) compréhensible par un non-technicien (ex: DSI d'une PME).
- **Contraintes de Performance :** SLA critique de **3 à 5 secondes maximum** pour la génération complète de l'explication (nécessite un LLM à grande vitesse de token/sec). Un Time-To-First-Token (TTFT) très bas est privilégié.
