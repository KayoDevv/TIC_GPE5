# Spécifications d'Intégration du Schema Registry (Pour l'Équipe Infrastructure)

Le projet repose sur une architecture orientée événements asynchrone pointue via Kafka. Pour garantir que les microservices (Workers Python & API Gateway) communiquent sans erreur de typage, **l'utilisation d'un Schema Registry est obligatoire pour l'ensemble des topics applicatifs.**

Ces spécifications définissent les exigences de déploiement, de configuration et le cycle de vie des schémas JSON (JSON Schema Draft-07) pour l'équipe en charge.

## 1. Exigences d'Infrastructure et de Déploiement

### 1.1 Composants Requis
- **Version recommandée :** Confluent Schema Registry (version compatible avec le cluster Kafka en place, ex: >= 7.4.x).
- **Format cible :** Strictement `JSON Schema` (et non Avro ou Protobuf dans un premier temps). Les payloads seront encodés nativement avec le "Magic Byte" (0x00) suivi de l'ID du schema (4 octets) tel que défini par le standard Confluent.
- **Stockage backend :** Le topic interne Kafka (généralement `_schemas`) doit être configuré avec un compactage de logs (`cleanup.policy=compact`) et un `replication.factor` >= 3 pour garantir la haute disponibilité.

### 1.2 Accessibilité & Sécurité
- Le Schema Registry doit exposer son API REST en interne pour l'application **(Port HTTP 8081 par défaut)**, mais **obligatoirement derrière TLS 1.3**.
- **Authentification :** L'authentification HTTP Basic (liée aux tokens/ACL Kafka) doit être mise en place pour que seuls les microservices autorisés puissent lire/écrire les schémas.

## 2. Stratégie de Typage et Règle d'Évolution (Compatibility Mode)

### 2.1 Sujet à configuration stricte
Le niveau de compatibilité pour **tous les sujets métiers (`*`)** doit être forcé à `BACKWARD` ou `FORWARD`.

- **Recommandation : `BACKWARD_TRANSITIVE`**
  Cela garantit que les consommateurs (ex: le *Verdict Engine* Verdict Layer) mettant à jour leur code pourront toujours lire les événements produits avec une *ancienne* version du schéma.
- En `BACKWARD`, un producteur ne peut **pas supprimer un champ obligatoire** ni **changer son type**, mais peut ajouter de nouveaux champs (optionnels).

### 2.2 Stratégie de nommage (Subject Name Strategy)
Le Schema Registry doit être configuré avec la stratégie de nommage par défaut : **`TopicNameStrategy`**.
- Un topic produit un seul type d'objet (ex: `VerdictResultEvent`).
- Le schéma pour la valeur du message sur le topic `verdict.result` sera identifié sous le sujet : `verdict.result-value`.

## 3. Définition des Contrats (Sujets à intégrer)

L'équipe applicative livre 5 schémas JSON situés dans `packages/kafka-schemas/` du monorepo :

| Topic Cible | Fichier Fourni | Sujet dans le Registry (-value) | Producteur (Write) | Consommateurs (Read) |
|---|---|---|---|---|
| `file.requested` | `file.requested.json` | `file.requested-value` | Backend Gateway | Layers 1 & 2 |
| `ml_layer.result` | `ml_layer.result.json` | `ml_layer.result-value` | ML Layer (ML) | Verdict Layer (Verdict) |
| `sandbox_layer.result` | `sandbox_layer.result.json` | `sandbox_layer.result-value` | Sandbox Layer (Sandbox) | Layers 3 & 4 |
| `llm_layer.result` | `llm_layer.result.json` | `llm_layer.result-value` | LLM Layer (LLM) | Verdict Layer (Verdict) |
| `verdict.result` | `verdict.result.json` | `verdict.result-value` | Verdict Layer (Verdict) | Backend / WebSocket |

*Note sur les clés Kafka :* Les clés des messages Kafka (ex: `job_id`) sont utilisées pour garantir l'ordre de traitement par un même consommateur sur une partition. L'enregistrement des schémas de clé (TopicName-key) n'est **pas requis** (elles peuvent être de simples strings UTF-8). Le Schema Registry gérera uniquement les **Values**.

## 4. Intégration dans le flux CI/CD (GitHub / GitLab)

Il incombe à la délégation de :
1. **Fournir un outil CI (ou module Terraform) pour la publication automatique :**
   Lorsque l'équipe de dev met à jour un fichier dans `packages/kafka-schemas/*.json` et pousse sur `main`, la CI doit invoquer l'API du Schema Registry (ou via Terraform Provider Confluent) pour enregistrer la nouvelle version.
   *Exemple d'appel REST attendu dans la CI :*
   ```bash
   curl -X POST -H "Content-Type: application/vnd.schemaregistry.v1+json" \
   --data '{"schema": "{\"type\": \"object\", ...}", "schemaType": "JSON"}' \
   http://schema-registry:8081/subjects/ml_layer.result-value/versions
   ```

2. **Validation avant déploiement (Dry-Run CI) :**
   Lorsqu'un développeur fait une Pull Request (PR) modifiant un `*.json`, la CI doit effectuer un appel API de test de compatibilité :
   ```http
   POST /compatibility/subjects/{subject}/versions/latest
   ```
   Si la modification casse le contrat (ex: changement de type sur l'UUID), la CI doit échouer instantanément.

## 5. Livrables Attendus pour le Dev Applicatif

Pour que les développeurs puissent commencer à intégrer le code Python (`py-shared-core`), l'équipe en charge doit fournir :
1. **L'URL du point d'accès REST (Prod / Staging).**
2. **Les identifiants d'API associés (Basic Auth).**
3. **Le bloc docker-compose final du Schema Registry** (image Confluent officielle recommandée) validé, à inclure dans le repo pour les développeurs locaux.
