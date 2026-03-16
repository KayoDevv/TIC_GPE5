# Spécifications Techniques Kafka : Zero-Trust

## 1. Configuration Globale du Cluster Kafka
Le cluster Kafka agit comme le bus de messages central de l'architecture orientée événements.

- **Sécurité en transit :** Le chiffrement TLS 1.3 est strictement obligatoire pour toutes les communications entre les microservices (Producers/Consumers) et les brokers Kafka.
- **Rétention des données (RGPD) :** Une politique de rétention agressive doit être configurée au niveau des brokers ou des topics. Les pièces jointes et les logs de session non-critiques doivent subir une destruction absolue au bout de 60 minutes maximum. Configurez `retention.ms=3600000`.
- **Infrastructure :** Le cluster Kafka doit être géré et provisionné via Terraform dans le cadre de l'approche Infrastructure as Code (IaC).

## 2. Spécifications des Topics et Contrats de Données
Le pattern "Scatter-Gather" nécessite une définition stricte des topics. L'utilisation d'un Schema Registry est requise pour figer les contrats d'interface.

| Topic | Producteur | Consommateurs | SLA Associé | Contenu Exigé (Schema) |
|---|---|---|---|---|
| `file.requested` | Backend Gateway | ML Layer, Sandbox Layer | N/A | URL S3 du fichier, empreintes cryptographiques (SHA-256), contexte (corps de l'email). |
| `ml_layer.result` | ML Layer | Verdict Layer (Verdict Engine) | < 500 ms | Score de risque (0-100) et tags d'analyse statique. |
| `sandbox_layer.result` | Sandbox Layer | LLM Layer, Verdict Layer | < 120 s | Rapport JSON structuré, Indicateurs de Compromission (IOC) classés par tactique MITRE ATT&CK. Doit inclure le contexte de l'email pour le LLM Layer. |
| `llm_layer.result` | LLM Layer | Verdict Layer (Verdict Engine) | 3 à 5 s | Décision binaire (Malveillant/Sain) et chaîne de caractères explicative en langage naturel générée par le LLM. |

## 3. Gestion des Consumer Groups et Scalabilité
La scalabilité dynamique est l'un des enjeux majeurs, particulièrement pour le Sandbox Layer (Sandbox) qui est lourd en ressources.

- **Consumer Groups :** Chaque microservice Python doit consommer les événements en parallèle en utilisant des Consumer Groups Kafka distincts.
- **Auto-scaling Kubernetes :** Vous devez configurer une métrique d'alerting (via Prometheus) basée sur le Consumer Lag (retard de traitement) du topic `file.requested` pour le groupe du Sandbox Layer. Si ce lag dépasse un seuil défini, Kubernetes doit automatiquement déployer de nouveaux Pods de Sandbox.
- **Gestion des Timeouts (Pattern Saga) :** Le Verdict Engine (Verdict Layer) attend les réponses des workers Kafka. Si le message de retour du Sandbox Layer n'apparaît pas dans `sandbox_layer.result` après 125 secondes, l'intégrateur Kafka/Backend doit prévoir que le Verdict Layer émette un statut de "Timeout Sandbox".

## 4. Tâches pour l'Intégration CI/CD et IaC
Le déploiement et la gestion de l'infrastructure Kafka doivent être entièrement automatisés.

- **Terraform (IaC) :** Écrire les modules Terraform pour provisionner le cluster Kafka géré, configurer les Topics avec leurs partitions, et instancier le Schema Registry.
- **Validation des Schémas dans la CI :** Intégrer une étape dans GitHub Actions ou GitLab CI pour valider les évolutions des schémas (compatibilité ascendante/descendante) avant le déploiement.
- **Tests Asynchrones :** S'assurer que les tests unitaires (via pytest-asyncio) et les pipelines TDD pour les workers valident correctement la publication et la consommation des messages Kafka.
- **Monitoring :** Déployer les exportateurs Kafka pour Prometheus afin de remonter les métriques dans les tableaux de bord Grafana pour l'équipe SecOps.
