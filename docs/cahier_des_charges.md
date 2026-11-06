# Cahier des Charges Complet : Charon — Extension de Sécurité Browser

## 1. Contexte et Vision

### Présentation du projet
- **Nom du projet :** Charon (anciennement nom de code « Zero-Trust »).
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
- **Temps de réponse max (Sandbox) :** < 300 secondes (timeout dur harmonisé, voir §6 et §9).
- **Adoption :** 100% de la flotte d'ordinateurs déployée via les MDM (Mobile Device Management).

## 3. Périmètre du projet

### Inclus (Scope)
- Extension pour Google Chrome et Microsoft Edge (Manifest V3).
- Support strict des Webmails : Gmail et Outlook Web.
- Analyse des pièces jointes au format Fichier (Office, PDF, Exécutables, Archives).
- Tableau de bord basique pour l'administrateur (Logs des alertes et IOCs).
- **Site vitrine (Nuxt 4)** servant l'extension packagée (zip conforme MV3) aux utilisateurs.
- **Chaîne CI de sécurité** : analyse statique (SAST), analyse des dépendances (SCA) et scan d'images **Trivy**, plus la validation du contrat inter-couches.
- **Sinkhole DNS** (inetsim) pour l'observation réseau contrôlée pendant la détonation.

### Exclus (Hors Scope pour la V1)
- Analyse des liens (URL scanning) dans le corps de l'email.
- Clients lourds de messagerie (Outlook Desktop App, Apple Mail).
- Remédiation automatique sur le poste de travail (le périmètre est limité à l'analyse et au blocage du téléchargement).
- **Déploiement administré via GPO / console Google Workspace** : reporté en V2. La V1 distribue l'extension packagée via le site vitrine.

## 4. Analyse des besoins

### Cibles et Utilisateurs
- **Persona 1 : "Alice" (Utilisatrice standard).** Elle veut juste ouvrir sa facture. Elle déteste quand l'ordinateur bloque pour rien. Elle a besoin du système de validation visuelle et d'explications simples.
- **Persona 2 : "Bob" (Admin IT / SecOps).** Il a besoin de voir les Indicateurs de Compromission (IOC) capturés par la Sandbox dans une console d'administration pour la réponse à incident.

### Besoins fonctionnels
- **F1 :** Interception automatique du clic de téléchargement via les content scripts (Gmail et Outlook Web). *Exigence cible ; voir Annexe A #2 pour l'état d'implémentation.*
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
- **Stockage :** **MinIO** (StatefulSet in-cluster), accès aux samples par presigned URL, rétention **120 min**.

### Données et RGPD
- **Politique de rétention :** Destruction absolue des pièces jointes et des logs de session non-critiques au bout de **120 minutes**.
- **Conservation des métadonnées :** Uniquement les empreintes cryptographiques (SHA-256) et les données anonymisées pour le réentrainement des modèles ML.

## 6. Spécifications détaillées des Couches d'Analyse (Layers)

Chaque Layer est un microservice Python indépendant consommant les événements Kafka en parallèle. Les deux analyses initiales (ML et Sandbox) s'exécutent **en parallèle** sur `file.requested` ; le LLM n'est invoqué que conditionnellement (voir LLM Layer).

### ML Layer : Static & ML Service (Le Filtre Rapide)
- **Rôle :** Filtrage ultra-rapide des PDF par analyse statique ; sert de "Fast-Track" pour les fichiers légitimes évidents. **Consultatif** : son score ne bloque pas seul (voir Verdict Engine).
- **Processus technique :**
    - Extraction d'environ **30 features statiques PDF** avec **pikepdf** (jeu de features inspiré de **CIC-Evasive**), bornée par un budget temps : structure (objets, streams, pages, updates incrémentaux, tailles, fonts/images/annotations/liens), actions actives (`/JavaScript`, `/OpenAction`, `/AA`, `/Launch`, `/SubmitForm`, `/GoToR`, JS suspect : `eval`/`unescape`/`fromCharCode`), entropie globale et de flux, couches d'encodage, URLs (total, externes, domaines distincts).
    - Inférence ML : vecteur de features passé dans un modèle tabulaire **LightGBM compilé en ONNX** (ONNX Runtime). Un **sidecar `feature_order`** est validé au démarrage pour garantir que l'inférence voit exactement le vecteur d'entraînement.
    - **Abstention :** pour tout type de fichier non-PDF, le ML Layer s'abstient (statut différent de `completed`, score sans opinion) et laisse la décision aux autres couches.
    - *Contrainte de déploiement :* les wheels NumPy 2.x (baseline x86-64-v2) crashent sur la VM cible (x86-64-v1) → **numpy figé < 2**.
- **SLA de traitement :** < 500 millisecondes.
- **Sortie Kafka (`ml_layer.result`) :** Score de risque (0-100) et tags statiques.

### Sandbox Layer : Dynamic Sandbox Service (L'Analyse Comportementale)
- **Rôle :** Exécuter le fichier dans un environnement contrôlé pour capturer les actions malveillantes non-visibles statiquement (obfuscation, payloads téléchargés au runtime, JavaScript auto-exécuté).
- **Orchestration :** K3s mono-nœud (Debian natif). Le consumer Kafka crée **un Job `batch/v1` éphémère par sample**, **routé par magic bytes** :
    - `\x7fELF` → image `ubuntu-sandbox` + `run_analysis.py`
    - `%PDF` / inconnu/déguisé → image `ubuntu-pdf-sandbox` (mupdf 1.24.10 + Node/PDF.js + pdfid + qpdf) + `run_pdf_analysis.py`
    - Chaque image porte son propre **tag de release immuable** (`ubuntu-sandbox:v1.2.x`, `ubuntu-pdf-sandbox:v1.2.x`), déclaré dans l'en-tête `ghcr-image` de son Dockerfile et pré-chargé dans containerd : les Jobs sont sans credentials et ne peuvent pas puller.
- **Isolation & durcissement :**
    - **gVisor (runsc) obligatoire** — imposé par une **ValidatingAdmissionPolicy fail-closed** : aucun Job de détonation n'est admis sans le RuntimeClass gVisor (isolation kernel user-space).
    - **Egress-gate (initContainer fail-closed)** : avant toute détonation, un initContainer sonde une cible externe et ne laisse démarrer le container d'analyse que lorsque l'egress est **prouvé bloqué** ; sinon le pod échoue. Parade à la race de programmation de la NetworkPolicy Calico — le sample ne s'exécute jamais tant que l'egress est ouvert.
    - `cap-drop ALL` (sauf `SYS_PTRACE` pour strace), utilisateur non-root (UID 10001), rootfs read-only, NetworkPolicy deny-all (enforcement Calico), namespace dédié. **seccomp : `RuntimeDefault`** *(le profil whitelist `charon-seccomp.json` est à auditer avant activation — voir Annexe A #17)*. Leurres anti-sandbox dans l'image (faux fichiers utilisateur, faux historique bash).
- **Collecte comportementale :**
    - **State-diff :** snapshot avant/après (FS hashé SHA-256 sur `/etc /home /tmp /var /opt /root`, process, sockets, crontab, systemd, chemins de persistance), diff des changements significatifs, **baseline du harnais soustraite**.
    - **Syscalls via `strace -f`** sur les processus de détonation (`mutool draw`, `node pdf_runner.js`) — capture `execve`/`connect`/`openat`/`mprotect`/`ptrace`. *(eBPF/bpftrace envisagé en V2.)*
    - **PDF — couche dynamique :** `mutool draw` (rendu, exerce zlib/JPEG/JBIG2) + `node pdf_runner.js` (exécute le JS embarqué dans un `vm` Node à contexte Adobe stubbé → `app.launchURL`/`submitForm` déclenchent de **vrais** syscalls réseau observables). *La capture réseau complète (PCAP/INetSim dans l'agent) est un écart ouvert — voir Annexe A #18.*
- **Scoring (defense-in-depth) :**
    - 5 sondes statiques PDF : `pdfid`, entropie locale, magic embarqué (ELF/PE/ZIP), actions `/URI` (phishing), anomalies structurelles.
    - 7 hypothèses comportementales sur les syscalls : persistance, C2, injection, chiffrement, évasion, propagation, lolbins.
    - `anomaly_score` = somme pondérée. **Verdict à 3 bandes** : `malicious` (≥ 0,15, signal fort), `needs_more_context` (≥ 0,04, ambigu → escaladé au LLM avec l'`email_context`), `benign` (sinon).
    - **Garde D1 (silence ≠ sain) :** en l'absence d'exécution réellement observée (`no_liveness`, `analysis_error`), le verdict monte à `needs_more_context` — **jamais `benign`**.
- **SLA de traitement :** **timeout dur 300s** (`SANDBOX_TIMEOUT_S`, `activeDeadlineSeconds`), GC du Job via `ttlSecondsAfterFinished`. **Tous les timeouts de la chaîne sont alignés sur cette valeur de 300s** (Job deadline ≥ reaper Verdict ≥ timeout sandbox). Le dépassement est géré par le **reaper du Verdict Layer** — il n'existe pas de message `timeout_with_partial` émis par l'agent ; jamais de blocage de l'agrégateur.
- **Sortie Kafka (`sandbox_layer.result`) :** rapport JSON — `verdict`, `iocs` classés par tactique **MITRE ATT&CK**, `behavior_summary`, `_meta` (`anomaly_score`, scores par hypothèse).

### LLM Layer : LLM Cognitive Service (L'Analyste Sémantique)
- **Rôle :** Corréler le contexte initial avec les résultats techniques pour déterminer l'intention réelle, et générer une explication claire.
- **Invocation conditionnelle :** le LLM Layer n'est appelé **que** sur la bande `needs_more_context` du Sandbox Layer — jamais sur un verdict terminal (`benign`/`malicious`/`error`).
- **Processus technique :**
    - Ingère le corps de l'email (contexte) ET le rapport technique JSON du Sandbox Layer.
    - Modèle **Llama-3.3-70B** via un **routeur Hugging Face (API REST)** vers une instance dédiée.
    - Prompting technique : identifier les incohérences (ex : "L'email prétend être une facture PDF, mais la sandbox indique que le processus a ouvert PowerShell et tenté une connexion externe").
- **SLA de traitement :** 3 à 5 secondes.
- **Sortie Kafka (`llm_layer.result`) :** avis (Malveillant/Sain) **consultatif** + explication en langage naturel. La bande `needs_more_context` n'est **jamais bloquée d'office** : le LLM rend un avis et le verdict s'affiche en **orange (avertissement)** plutôt qu'en blocage.

### Verdict Layer : Verdict Engine (Le Moteur d'Agrégation)
- **Rôle :** Consolider les réponses asynchrones et appliquer la politique de sécurité globale.
- **Processus technique :**
    - Implémentation du pattern **Saga**, état conservé dans **Redis**.
    - **Matrice de décision (ordre de précédence réel) :** ① LLM « malveillant » → bloqué ; ② Sandbox `malicious` → bloqué (sans même appeler le LLM) ; ③ Sandbox timeout → bloqué/averti, Sandbox `error` → averti ; ④ le **score ML est consultatif** : au-dessus de **90** il élève un verdict sain en **avertissement**, il ne **bloque seul qu'au-dessus de 98** et uniquement si l'analyse comportementale est partielle ; ⑤ sinon → autorisé. Un blocage dicté par la Sandbox ne peut jamais être annulé par le LLM.
    - **Gestion des Timeouts (reaper) :** si le Sandbox Layer ne répond pas dans la fenêtre alignée sur le timeout sandbox (**300s**), le Verdict Engine émet un statut "Suspect par défaut - Timeout Sandbox" pour éviter un blocage indéfini du Front.

## 7. Contraintes

### Contraintes techniques
- **Manifest V3 :** Obligatoire pour l'extension Chrome. Les Service Workers du navigateur ont une durée de vie limitée, nécessitant une gestion fine de la reconnexion des WebSockets (ping keepalive 25s, reconnexion en backoff exponentiel, état persisté dans `chrome.storage.session`).
- **Limites de taille :** 35 Mo maximum par upload. 200 Mo maximum de décompression pour les archives (limite de 3 niveaux de profondeur récursive pour contrer les attaques par Zip Bomb).

## 8. UX et UI
- **Design System :** Composants injectés dans le "Shadow DOM" pour ne pas hériter ou interférer avec les styles CSS natifs de Gmail ou Outlook.
- **Interface Utilisateur - Composant de Validation :**
    - Vert (Autorisé) : Le bouton de téléchargement natif est déverrouillé.
    - Rouge (Bloqué) : Le téléchargement est rendu inopérant.
    - Orange (Avertissement) : Affichage d'un panneau latéral contenant l'explication générée par le LLM Layer, avec option de forçage (si autorisé par l'admin). La bande `needs_more_context` s'affiche en orange, jamais en blocage automatique.

## 9. Sécurité
- **Protection en transit :** TLS 1.3 obligatoire, WebSockets sécurisées (WSS). *Cible production ; en dev, Kafka est en PLAINTEXT et l'ingress non vérifié — à finaliser avant la mise en production (voir Annexe A #23).*
- **Isolation stricte :** containers durcis sur K3s — **gVisor (runsc) obligatoire via ValidatingAdmissionPolicy fail-closed** + egress-gate fail-closed + seccomp (`RuntimeDefault`) + `cap-drop ALL` (sauf `SYS_PTRACE`) + non-root (UID 10001) + rootfs read-only + NetworkPolicy deny-all (Calico) + namespace dédié. Chaque Job est détruit après exécution (`ttlSecondsAfterFinished`).
- **Authentification :** JWT tokens émis via une politique Single Sign-On (SSO) d'entreprise. *À finaliser avant prod : la récupération JWKS et la sortie du mode `AUTH_DEV_MODE` sont requises (voir Annexe A #22).*

## 10. Performance
- **Temps de réponse cible :** 90% des fichiers (sains connus, cache hit Redis, ou analysables statiquement trivialement) doivent être traités et validés par le ML Layer en moins de 2 secondes.
- **Scalabilité :** Kafka avec Consumer Groups. **KEDA** augmente automatiquement les réplicas du Sandbox Layer en lisant directement le _lag_ Kafka (pas besoin d'exporter les métriques pour le scaling).

## 11. Qualité et tests
- **Stratégie d'implémentation :** Test Driven Development (TDD).
- **Tests unitaires :** `pytest` avec `pytest-asyncio` ; couverture visée à 100%.
- **Tests E2E :** Automatisation via `Playwright` pour simuler le parcours utilisateur. *Exigence cible ; l'E2E Playwright reste à implémenter (actuellement Vitest côté front — Annexe A #31).*
- **Recette métier :** Soumission automatisée d'un dataset de 10 000 échantillons mixtes pour certifier les seuils de détection et le taux de faux positifs (< 0,5%). *Outillage présent ; campagne à lancer et chiffres à publier (Annexe A #32).*

## 12. Déploiement
- **CI/CD :** Pipeline automatisé (GitHub Actions) incluant le linting strict (Ruff / MyPy), les **scans de sécurité (SAST, SCA, Trivy)**, les tests unitaires, le build d'images Docker et la publication d'**images immuables sur GHCR**.
- **Infrastructure as Code (IaC) :** **Terraform pour le cluster K3s on-prem** (namespaces, RBAC, NetworkPolicies, Helm) — pas d'EKS/GKE ni de Kafka managé.
- **Déploiement Extension :** **V1 — distribution de l'extension packagée (zip conforme MV3) via le site vitrine Nuxt.** V2 — déploiement administré silencieux via GPO (postes Windows) ou console Google Workspace.

## 13. Maintenance et Évolutions
- **SLA (Service Level Agreement) :** Disponibilité de l'API Gateway requise à 99.9%.
- **Roadmap future (V2) :** Analyse OCR des images intégrées dans les emails ; déploiement GPO/Workspace ; capture réseau PCAP complète dans l'agent ; cache Redis par empreinte ; eBPF.
- **Supervision :** Monitoring avec Prometheus, tableaux de bord Grafana, alerting SecOps. *L'export des métriques Kafka vers Prometheus est optionnel (désactivé par défaut) : KEDA lit le lag directement ; l'activer n'est requis que pour les tableaux de bord (Annexe A #30).*

## 14. Risques
- **Risque technique (Hallucination IA) :** Le LLM pourrait minimiser la gravité d'un fichier malveillant complexe.
    - _Mitigation :_ L'architecture relègue le LLM à un rôle **explicatif et consultatif**, invoqué seulement sur `needs_more_context`. La matrice de décision du Verdict Engine garantit qu'un blocage dicté par les IOCs de la Sandbox ne peut pas être annulé par le LLM.
- **Risque financier (Coûts Cloud) :** Explosion des coûts d'infrastructure liés à la consommation CPU/RAM des containers de détonation et du LLM.
    - _Mitigation :_ Mise en cache agressive (Redis) des empreintes de fichiers sains, et optimisation de l'early-exit au niveau du ML Layer.

## 15. Livrables attendus
- Code source complet structuré en monorepo documenté (Extension Front, API Gateway, Workers Layers 1/2/3, Verdict Engine, site vitrine Nuxt).
- Définitions d'architecture (Manifestes Kubernetes `.yaml` pour K3s, Topics Kafka provisionnés via le chart Bitnami). Schémas d'échange **JSON versionnés** (`packages/kafka-schemas/`), contrat inter-couches validé en CI — **pas de Schema Registry au runtime** (retiré post-pivot Bitnami ; les 2 documents mentionnant encore le Schema Registry sont à archiver).
- Extension packagée prête pour le déploiement (zip conforme Manifest V3, servie par le site vitrine).
- Documentation complète de déploiement, diagrammes de séquence et Runbook d'exploitation niveau 2.

## 16. Clarifications Opérationnelles
- **Mode Dégradé (Circuit-Breaker) :** En cas d'indisponibilité de la Sandbox ou de dépassement des quotas, le système bascule en "Mode Dégradé" : l'analyse repose alors uniquement sur le ML Layer, accompagnée d'une **notification visuelle orange** (vérification partielle). Le mode dégradé **ne bloque pas d'office** ; de même, la bande `needs_more_context` n'est jamais bloquée automatiquement — le LLM rend un avis consultatif.

---

## Annexe A — Journal des décisions & écarts (code ↔ cahier des charges)

Revue du 2026-10-22. Légende des verdicts : **V** = le choix du code est validé, le cahier des charges a été aligné ci-dessus ; **C** = le cahier des charges reste la cible, le **code doit être corrigé** ; **X** = hors périmètre V1 ; **Audit/Ouvert** = point à trancher.

### 1 · Périmètre et produit
| # | Sujet | Verdict | Action | Prio |
|---|---|---|---|---|
| 1 | Nom « Zero-Trust » → « Charon » | V | CDC renommé en Charon (§1) | P3 |
| 2 | F1 : interception du clic (Gmail/Outlook) vs glisser-déposer | **C** | Code à corriger : implémenter l'interception, ou basculer F1 en V2 | P1 |
| 3 | Types : Office/PDF/exécutables/archives vs ML PDF seul + Sandbox ELF+PDF | **C** | Code : étendre la couverture (Office, archives) pour tenir le CDC | P2 |
| 4 | Archives 200 Mo / 3 niveaux : aucune gestion | **C** | Code : implémenter la décompression bornée anti-zip-bomb | P3 |
| 5 | Console admin « Bob » (IOC/logs) : seul Grafana existe | **C** | Code : construire la console admin V1 | P2 |
| 6 | Extension `.crx` via GPO/Workspace vs zip servi par le site Nuxt | **X** | Hors périmètre V1 : V1 = zip via le site, GPO/Workspace → V2 (§3, §12) | P3 |
| 7 | Site Nuxt, sinkhole, pipeline de validation, CI SAST/SCA/Trivy (absents) | V | Ajoutés au CDC (§3, §12) | P3 |

### 2 · Décision et couches d'analyse
| # | Sujet | Verdict | Action | Prio |
|---|---|---|---|---|
| 8 | ML : SHA-256/SSDeep/ImpHash/OLE-VBA/PE vs modèle ONNX 30 features PDF + abstention | V | §6 ML réécrit (30 features pikepdf, LightGBM→ONNX, abstention non-PDF) | P3 |
| 9 | « Score ML > 90 bloque » vs ML consultatif (>90 warning, >98 solo si sandbox partielle) | V | §6 Verdict aligné sur la logique réelle ; corriger aussi le README | P2 |
| 10 | Timeout sandbox → « suspect » ; option « par tenant » inexistante (réglage global) | V (à vérifier) | CDC : timeout global, pas « par tenant » | P3 |
| 11 | LLM Llama 3 8B via vLLM/gRPC vs Llama-3.3-70B via routeur HF (REST) | V | §6 LLM aligné (70B, HF REST) | P1 |
| 12 | Mode dégradé / needs_more_context | **Décision** | Ne bloque pas d'office : le LLM donne un avis → orange (§6, §8, §16) | P1 |
| 13 | LLM sur toutes les analyses (implicite) vs seulement `needs_more_context` | V | §6 LLM : invocation conditionnelle | P3 |

### 3 · Sandbox
| # | Sujet | Verdict | Action | Prio |
|---|---|---|---|---|
| 14 | Timeouts incohérents (template 180s, `SANDBOX_TIMEOUT_S=300`, Job 360s, verdict 125s, WS 150s) | **C — fix critique** | **Harmoniser toute la chaîne sur 300s** ; CDC §2/§6/§9 passés à 300s | P1 |
| 15 | Message `timeout_with_partial` inexistant (reaper du Verdict Layer) | V | §6 : le reaper du Verdict Layer gère le timeout | P2 |
| 16 | gVisor « activable » vs obligatoire (ValidatingAdmissionPolicy fail-closed) | V | §6/§9 : gVisor obligatoire | P3 |
| 17 | Seccomp liste blanche : `RuntimeDefault` actif, `charon-seccomp.json` inactif | **Audit** | Auditer la meilleure solution avant d'activer le profil whitelist | P2 |
| 18 | Appels réseau « observables » : sinkhole sur DNS, pas de PCAP/INetSim dans l'agent | **C** | Code : ajouter la capture réseau (PCAP) dans l'agent | P2 |
| 19 | Garde D1 « silence ≠ sain » + egress-gate (absents) | V | Ajoutés au CDC (§6, §9) | P3 |

### 4 · Sécurité, RGPD, infrastructure
| # | Sujet | Verdict | Action | Prio |
|---|---|---|---|---|
| 20 | Destruction des pièces jointes : **RGPD = 120 min** (MinIO sans règle d'expiration) | V (valeur corrigée) | CDC passé à 120 min ; **code : ajouter la règle d'expiration MinIO** (120 min) | P1 |
| 21 | Logs non-critiques détruits à 120 min vs Loki 48h | **C** | Code : réduire la rétention Loki à 120 min (ou classifier les logs) | P2 |
| 22 | JWT via SSO : JWKS `NotImplementedError`, `AUTH_DEV_MODE`, extension `anonymous` | **C** | Code : implémenter JWKS/SSO avant prod | P1 |
| 23 | TLS 1.3 partout : Kafka en PLAINTEXT, ingress non vérifié | **À la fin** | Finaliser TLS prod avant mise en production ; dev reste permissif | P1 |
| 24 | Terraform EKS/GKE + Kafka managé vs K3s on-prem | V | §12 aligné sur K3s on-prem | P3 |
| 25 | Réplication Kafka 3 (README) vs 1 (mono-nœud) + KEDA | V | CDC : KEDA (§5/§10) ; corriger le README Kafka | P3 |
| 26 | Clé Kafka = `job_id` vs `send_and_wait` sans clé | **C** | Code : fixer la clé de partition (`job_id`) | P2 |
| 27 | Adresse Kafka par défaut du LLM `kafka:9092` (fail-ouvert) | **C** | Code : durcir la configuration (fail-closed sur adresse manquante) | P3 |
| 28 | Schema Registry (docs/architecture) déjà supprimé | V | Archiver les 2 docs résiduels (§15) | P3 |

### 5 · Performance et qualité
| # | Sujet | Verdict | Action | Prio |
|---|---|---|---|---|
| 29 | Cache Redis des empreintes saines (KPI 90% < 2s) : aucun cache par empreinte | **C** | Code : implémenter le cache par empreinte, ou retirer le KPI | P2 |
| 30 | Export Kafka pour Prometheus désactivé (KEDA lit le lag directement) | **V + C** | V pour le scaling ; C (activer l'export) seulement si tableau de bord voulu (§10/§13) | P3 |
| 31 | Tests E2E Playwright : seul Vitest existe | **C** | Code : ajouter la suite E2E Playwright | P2 |
| 32 | Recette 10 000 échantillons / faux positifs < 0,5% : outillage présent, pas de résultats | **C** | Lancer la campagne de recette et publier les chiffres | P1 |
