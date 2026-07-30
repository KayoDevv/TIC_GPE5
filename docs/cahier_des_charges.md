# Cahier des Charges Complet : Extension de Sécurité Browser

## 1. Contexte et Vision

### Présentation du projet
- **Nom du projet :** Zero-Trust (Nom de code)
- **Contexte de création :** Les attaques par spear-phishing et malwares polymorphes contournent de plus en plus les antivirus classiques basés sur des signatures statiques.
- **Problème identifié :** Les utilisateurs manquent de sensibilisation sur les conséquences de leurs actes.
- **Opportunité business :** Créer une solution B2B SaaS transparente pour l'utilisateur, combinant la rapidité de l'IA et la profondeur de la Sandbox.

### Vision stratégique
- **Positionnement marché :** Outil de cybersécurité "Endpoint" de nouvelle génération, axé sur la pédagogie et la "Défense en Profondeur".
- **Proposition de valeur :** "La puissance d'une équipe de cybersécurité SOC dans votre navigateur, analysant chaque pièce jointe en temps réel."
- **Différenciation :** L'utilisation d'un LLM pour vulgariser le rapport technique d'une Sandbox en langage clair pour l'utilisateur.

## 2. Objectifs du projet

### Objectifs principaux
- **Objectif business :** Réduire de 99% les infections par ransomware via email dans l'entreprise cible.
- **Objectif technique :** Ne jamais bloquer le navigateur de l'utilisateur (approche 100% asynchrone).
- **Objectif UX :** Rendre les alertes de sécurité compréhensibles par un employé non-technique.

### KPIs et Critères de succès
- **Taux de faux positifs :** < 0.5% (critique pour ne pas frustrer les utilisateurs).
- **Temps de réponse médian (ML seul) :** < 2 secondes.
- **Temps de réponse max (Sandbox) :** < 120 secondes.
- **Adoption :** 100% de la flotte d'ordinateurs déployée via les MDM (Mobile Device Management).

## 3. Périmètre du projet

### Inclus (Scope)
- Extension pour Google Chrome et Microsoft Edge (Manifest V3).
- Support strict des Webmails : Gmail et Outlook Web.
- Analyse des pièces jointes au format Fichier (Office, PDF, Exécutables, Archives).
- Tableau de bord basique pour l'administrateur (Logs des alertes et IOCs).

### Exclus (Hors Scope pour la V1)
- Analyse des liens (URL scanning) dans le corps de l'email.
- Clients lourds de messagerie (Outlook Desktop App, Apple Mail).
- Remédiation automatique sur le poste de travail (le périmètre est limité à l'analyse et au blocage du téléchargement).

## 4. Analyse des besoins

### Cibles et Utilisateurs
- **Persona 1 : "Alice" (Utilisatrice standard).** Elle veut juste ouvrir sa facture. Elle déteste quand l'ordinateur bloque pour rien. Elle a besoin du système de validation visuelle et d'explications simples.
- **Persona 2 : "Bob" (Admin IT / SecOps).** Il a besoin de voir les Indicateurs de Compromission (IOC) capturés par la Sandbox dans une console d'administration pour la réponse à incident.

### Besoins fonctionnels
- **F1 :** Interception automatique du clic de téléchargement via les content scripts.
- **F2 :** Upload du fichier de manière sécurisée directement vers l'Object Storage, sans passer par les serveurs de messagerie.
- **F3 :** Traitement dans une file d'attente asynchrone distribuée pour scaler la charge.
- **F4 :** Traduction des logs techniques de la Sandbox en résumé humain par le LLM.

## 5. Spécifications techniques globales

### Architecture (Event-Driven Microservices)
- **Type :** Microservices orientés événements avec pattern Scatter-Gather.
- **Orchestration :** Kubernetes **K3s** (mono-nœud, Debian natif) avec **Calico comme unique CNI** (namespace `calico-system`) — il assure à la fois le dataplane pod **et** l'enforcement des NetworkPolicies ; K3s est installé avec `--flannel-backend=none --disable-network-policy`, donc flannel est **désactivé**. Autoscaling **KEDA** sur le lag Kafka.
- **Bus de messages :** Apache Kafka — chart **Bitnami** (mode KRaft, mono-broker, in-cluster), topics provisionnés par le chart.
- **Frontend :** Vue 3 + WXT (TypeScript, Tailwind).
- **Backend Gateway :** Python (FastAPI) — émet l'événement `file.requested` sur Kafka après upload MinIO.
- **Base de données / Cache :** Redis pour le suivi des états et la gestion des WebSockets.
- **Stockage :** **MinIO** (StatefulSet in-cluster), accès aux samples par presigned URL, rétention 60 min.

### Données et RGPD
- **Politique de rétention :** Destruction absolue des pièces jointes et des logs de session non-critiques au bout de 60 minutes.
- **Conservation des métadonnées :** Uniquement les empreintes cryptographiques (SHA-256) et les données anonymisées pour le réentrainement des modèles ML.

## 6. Spécifications détaillées des Couches d'Analyse (Layers)

Chaque Layer est un microservice Python indépendant consommant les événements Kafka en parallèle.

### ML Layer : Static & ML Service (Le Filtre Rapide)
- **Rôle :** Filtrage ultra-rapide, détection des menaces connues et analyse structurelle préliminaire. Sert de "Fast-Track" pour les fichiers légitimes évidents.
- **Processus technique :**
    - Calcul d'empreintes (SHA-256, SSDeep, ImpHash).
    - Extraction structurelle : OLE/VBA pour Office, Header/Sections pour les PE (exécutables), Objets JS pour les PDF.
    - Calculs statistiques : Entropie du fichier (détection de packers/chiffrement).
    - Inférence ML : Passage des features dans un modèle de Machine Learning tabulaire (LightGBM ou Random Forest via ONNX Runtime).
- **SLA de traitement :** < 500 millisecondes.
- **Sortie Kafka :** Score de risque (0-100) et tags statiques.

### Sandbox Layer : Dynamic Sandbox Service (L'Analyse Comportementale)
- **Rôle :** Exécuter le fichier dans un environnement contrôlé pour capturer les actions malveillantes non-visibles statiquement (obfuscation, payloads téléchargés au runtime, JavaScript auto-exécuté).
- **Orchestration :** K3s mono-nœud (Debian natif). Le consumer Kafka crée un Job `batch/v1` par sample, **routé par magic bytes** :
    - `\x7fELF` → image `ubuntu-sandbox` + `run_analysis.py`
    - `%PDF` / inconnu/déguisé → image `ubuntu-pdf-sandbox` (mupdf 1.24.10 + Node/PDF.js + pdfid + qpdf) + `run_pdf_analysis.py`
    - Chaque image porte son propre **tag de release immuable** (`ubuntu-sandbox:v1.2.0`, `ubuntu-pdf-sandbox:v1.2.1`), déclaré dans l'en-tête `ghcr-image` de son Dockerfile et pré-chargé dans containerd : les Jobs sont sans credentials et ne peuvent pas puller.
- **Isolation & durcissement :** runtime `runc` durci — seccomp, `cap-drop ALL` (sauf `SYS_PTRACE` pour strace), utilisateur non-root (UID 10001), NetworkPolicy deny-all (enforcement Calico), namespace dédié. **RuntimeClass gVisor (runsc) activable** via `SANDBOX_RUNTIME_CLASS=gvisor` (isolation kernel user-space, recommandée en prod ; non activée par défaut en dev par contrainte d'installation du runtime). Leurres anti-sandbox dans l'image (faux fichiers utilisateur, faux historique bash).
- **Collecte comportementale :**
    - **State-diff :** snapshot avant/après (FS hashé SHA-256 sur `/etc /home /tmp /var /opt /root`, process, sockets, crontab, systemd, chemins de persistance), diff des changements significatifs, **baseline du harnais soustraite** (les fichiers système et l'outillage de l'agent ne comptent pas comme signal).
    - **Syscalls via `strace -f`** sur les processus de détonation (`mutool draw`, `node pdf_runner.js`) — capture `execve`/`connect`/`openat`/`mprotect`/`ptrace`. *(eBPF/bpftrace envisagé en V2 ; strace retenu pour la portabilité.)*
    - **PDF — couche dynamique :** `mutool draw` (rendu, exerce zlib/JPEG/JBIG2, déclenche les CVE de parseur) + `node pdf_runner.js` (exécute le JS embarqué dans un `vm` Node à contexte Adobe stubbé → `app.launchURL`/`submitForm` déclenchent de **vrais** syscalls réseau observables).
- **Scoring (defense-in-depth) :**
    - 5 sondes statiques PDF : `pdfid` (règles combinatoires), entropie locale, magic embarqué (ELF/PE/ZIP), actions `/URI` (phishing — scan du contenu décompressé, hébergement jetable, params base64), anomalies structurelles (`missing_pdf_magic`, ratio obj/pages…).
    - 7 hypothèses comportementales sur les syscalls : persistance, C2, injection, chiffrement, évasion, propagation, lolbins.
    - `anomaly_score` = somme pondérée. **Verdict à 3 bandes** : `malicious` (signal fort), `needs_more_context` (ambigu → escaladé au LLM avec l'`email_context`), `benign`.
- **SLA de traitement :** timeout dur 120s (`activeDeadlineSeconds`), GC du Job `ttlSecondsAfterFinished: 120`. Au-delà : message `timeout_with_partial` — jamais de blocage de l'agrégateur.
- **Sortie Kafka (`sandbox_layer.result`) :** rapport JSON — `verdict`, `iocs` classés par tactique **MITRE ATT&CK**, `behavior_summary` (narratif clair pour le LLM/UI), `_meta` (`anomaly_score`, scores par hypothèse).

### LLM Layer : LLM Cognitive Service (L'Analyste Sémantique)
- **Rôle :** Corréler le contexte initial avec les résultats techniques pour déterminer l'intention réelle, et générer une explication claire.
- **Processus technique :**
    - Ingère le message Kafka contenant le corps de l'email (contexte) ET le rapport technique JSON généré par le Sandbox Layer.
    - Utilise un modèle LLM spécialisé (ex: Llama 3 8B auto-hébergé via vLLM ou gRPC vers une instance dédiée).
    - Prompting technique : Demande au modèle d'identifier les incohérences (ex: "L'email prétend être une facture PDF, mais la sandbox indique que le processus a ouvert PowerShell et tenté une connexion externe").
- **SLA de traitement :** 3 à 5 secondes.
- **Sortie Kafka :** Décision binaire (Malveillant/Sain) + String explicatif en langage naturel (destiné à l'UI Frontend).

### Verdict Layer : Verdict Engine (Le Moteur d'Agrégation)
- **Rôle :** Consolider les réponses asynchrones des 3 Layers et appliquer la politique de sécurité globale de l'entreprise.
- **Processus technique :**
    - Implémentation du pattern Saga. Conserve un état dans Redis en attendant le retour des 3 workers.
    - Matrice de décision : Les règles métiers prévalent. Par exemple, si le Sandbox Layer détecte un ransomware avéré, le verdict est instantanément bloqué, indépendamment de l'avis du LLM Layer.
    - Gestion des Timeouts : Si le Sandbox Layer ne répond pas au bout de 125s, le Verdict Engine émet un statut "Suspect par défaut - Timeout Sandbox" pour éviter un blocage indéfini du Front.

## 7. Contraintes

### Contraintes techniques
- **Manifest V3 :** Obligatoire pour l'extension Chrome. Les Service Workers du navigateur ont une durée de vie limitée, nécessitant une gestion fine de la reconnexion des WebSockets.
- **Limites de taille :** 35 Mo maximum par upload. 200 Mo maximum de décompression pour les archives (limite de 3 niveaux de profondeur récursive pour contrer les attaques par Zip Bomb).

## 8. UX et UI
- **Design System :** Composants injectés dans le "Shadow DOM" pour ne pas hériter ou interférer avec les styles CSS complexes natifs de Gmail ou Outlook.
- **Interface Utilisateur - Composant de Validation :**
    - Vert (Autorisé) : Le bouton de téléchargement natif est déverrouillé.
    - Rouge (Bloqué) : Le téléchargement est rendu inopérant.
    - Orange (Avertissement) : Affichage d'un panneau latéral contenant l'explication générée par le LLM Layer (LLM) avec option de forçage (si autorisé par l'admin).

## 9. Sécurité
- **Protection en transit :** TLS 1.3 obligatoire. WebSockets sécurisées (WSS).
- **Isolation stricte :** containers durcis sur K3s — `runc` + seccomp + `cap-drop ALL` + utilisateur non-root (UID 10001) + NetworkPolicy deny-all (enforcement Calico) + namespace dédié. **RuntimeClass gVisor (runsc) activable** (`SANDBOX_RUNTIME_CLASS=gvisor`) pour l'isolation kernel user-space — recommandée en production, activée selon la disponibilité du runtime sur le nœud. Chaque Job est détruit après exécution (`ttlSecondsAfterFinished: 120`).
- **Authentification :** JWT tokens émis via une politique Single Sign-On (SSO) d'entreprise.

## 10. Performance
- **Temps de réponse cible :** 90% des fichiers (fichiers sains connus, cache hit Redis, ou analysables statiquement de manière triviale) doivent être traités et validés par le ML Layer en moins de 2 secondes.
- **Scalabilité :** Utilisation de Kafka avec des Consumer Groups. Si le _lag_ de la file d'attente du Sandbox Layer augmente au-delà d'un seuil, Kubernetes déploie automatiquement de nouveaux Pods de Sandbox.

## 11. Qualité et tests
- **Stratégie d'implémentation :** Test Driven Development (TDD)
- **Tests unitaires :** Framework `pytest` avec `pytest-asyncio` pour les composants asynchrones.
- **Tests E2E :** Automatisation via `Playwright` pour simuler le parcours d'un utilisateur téléchargeant différents types de fichiers sur l'interface webmail.
- **Recette métier :** Soumission automatisée d'un dataset de 10 000 échantillons mixtes (Bénins / Malwares connus / Zero-Days récents) pour certifier les seuils de détection (True Positives) et les faux positifs.

## 12. Déploiement
- **CI/CD :** Pipeline automatisé (GitLab/GitHub, Argo) incluant le linting strict (Ruff / MyPy), les tests unitaires, le build d'images Docker, et la publication sur le registre.
- **Infrastructure as Code (IaC) :** Utilisation de Terraform pour provisionner les clusters Kubernetes (EKS/GKE), le cluster Kafka géré, et les buckets de stockage.
- **Déploiement Extension :** Déploiement administré silencieux via GPO (Group Policy Object) pour les postes Windows ou via la console d'administration Google Workspace.

## 13. Maintenance et Évolutions
- **SLA (Service Level Agreement) :** Disponibilité de l'API Gateway requise à 99.9%.
- **Roadmap future (V2) :** Analyse OCR des images intégrées dans le corps des emails pour bloquer les tentatives de phishing textuel dissimulées sous forme d'image.
- **Supervision :** Monitoring des métriques avec Prometheus. Tableaux de bord Grafana et alerting vers les canaux SecOps dédiés.

## 14. Risques
- **Risque technique (Hallucination IA) :** Le LLM pourrait minimiser la gravité d'un fichier malveillant complexe.
    - _Mitigation :_ L'architecture relègue le LLM à un rôle explicatif. La matrice de décision du Verdict Engine garantit qu'un blocage dicté par les IOCs de la Sandbox ne peut pas être annulé par le LLM.
- **Risque financier (Coûts Cloud) :** Explosion des coûts d'infrastructure liés à la consommation CPU/RAM des containers de détonation (sandbox) et des LLMs de grande taille.
    - _Mitigation :_ Stratégie de mise en cache agressive (Redis) des empreintes de fichiers sains, et optimisation de l'early-exit au niveau du ML Layer.

## 15. Livrables attendus
- Code source complet structuré en monorepo ou multi-repos documentés (Extension Front, API Gateway, Workers Layers 1/2/3, Verdict Engine).
- Définitions d'architecture (Manifestes Kubernetes `.yaml` pour K3s, Topics Kafka provisionnés via le chart Bitnami). Schémas d'échange **JSON versionnés** (`packages/kafka-schemas/`), contrat inter-couches validé en CI (`sandbox-llm-contract.yml`) — **pas de Schema Registry au runtime** (non utilisé, retiré post-pivot Bitnami).
- Extension packagée prête pour le déploiement (`.crx` ou zip conforme Manifest V3).
- Documentation complète de déploiement, diagrammes de séquence et Runbook d'exploitation pour le niveau 2.

## 16. Clarifications Opérationnelles
- **Gestion des dépassements capacitaires (Circuit-Breaker) :** En cas d'indisponibilité de l'infrastructure de la Sandbox ou de dépassement des quotas cloud, le système bascule automatiquement en "Mode Dégradé". L'analyse repose alors uniquement sur les résultats du ML Layer (ML Statique), accompagnés d'une notification visuelle à l'utilisateur indiquant une vérification partielle.
