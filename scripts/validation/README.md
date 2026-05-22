# Pipeline de validation sandbox

Mesure trois propriétés du sandbox layer sur un corpus :

- **A. Déterminisme** — même fichier rejoué 2 fois donne le même `anomaly_score` (tolérance Δ < 0.05)
- **B. Distribution** — histogramme stable des scores entre deux runs distincts (test de drift)
- **C. Justesse** — `precision` / `recall` / `F1` sur les samples labellisés `benign` / `malicious`

Tout l'état est dans `validation/feeder_state.duckdb` + `validation/results.duckdb`. Les runs sont idempotents : relancer reprend exactement là où on s'est arrêté, sans double envoi.

---

## Layout corpus

```
<corpus_root>/
├── benign/      ← fichiers non-malveillants
├── malicious/   ← fichiers malveillants
└── unknown/     ← non labellisés (tests A + B uniquement, exclus du F1)
```

Le label est déduit du **nom du sous-dossier de 1er niveau** — pas de fichier de métadonnées à maintenir.

> **Racine canonique unique : `scripts/validation/real_corpus/`.** C'est le défaut du Makefile et de `prepare_corpus.py`. Les samples sont des **vrais malwares** → le dossier est **gitignoré** (jamais committé). Ne pas recréer de `corpus/` ou `tmp/corpus/` parallèle : une seule source de vérité.

---

## Prérequis

```bash
# Kafka + MinIO sont in-cluster (Bitnami + MinIO StatefulSet) :
make bootstrap-in-cluster   # déploie Kafka + MinIO si pas déjà fait
make deploy-dev             # workers consumer + watcher
make install                # dépendances Python (aiokafka, minio, duckdb)
```

---

## Commande principale

```bash
make sandbox-validate CORPUS=<dir> RUN_ID=<id> REPS=<n> MAX_INFLIGHT=<n>
```

Enchaîne automatiquement :

```
=== [1/3] Feed  ===   → upload corpus MinIO + publie file.requested
=== [2/3] Collect === → s'arrête automatiquement quand tous les résultats sont reçus
=== [3/3] Rapport === → affiche sections A / B / C
```

Le validator s'arrête **automatiquement** dès que `matched = total jobs envoyés`.
(`matched` compte chaque résultat persisté en DB, **erreurs incluses** — les erreurs
sont un sous-ensemble de `matched`, pas un terme à additionner.)

### Exemples

```bash
# Test rapide 5 fichiers, 1 répétition
make sandbox-validate CORPUS=/tmp/mini RUN_ID=test1 REPS=1 MAX_INFLIGHT=2

# Test déterminisme 100 fichiers × 2 répétitions = 200 jobs
make sandbox-validate CORPUS=scripts/validation/real_corpus RUN_ID=runV1 REPS=2 MAX_INFLIGHT=7

# Sauvegarde rapport dans un fichier
make sandbox-validate CORPUS=scripts/validation/real_corpus RUN_ID=runV1 REPS=2 > validation/report_v1.md
```

---

## Préparer un corpus depuis des datasets externes (`prepare_corpus.py`)

Pioche aléatoirement N fichiers d'un dossier source et les copie dans le corpus, sous le bon sous-dossier de label. Le pattern **multi-sources** marche nativement : appeler plusieurs fois avec différents `--source` mais le **même `--output`**, chaque appel ajoute au sous-dossier correspondant (collision-safe).

### Options

| Argument | Défaut | Usage |
|---|---|---|
| `--source` | — (requis) | Dossier source contenant les samples |
| `--count` | 1000 | Nombre de fichiers à piocher |
| `--label` | `malicious` | Sous-dossier de label : `malicious` / `benign` / `unknown` |
| `--output` | `scripts/validation/real_corpus` | Dossier corpus cible (racine canonique) |
| `--seed` | — | Seed aléatoire pour reproductibilité |

### Cas d'usage multi-sources

```bash
# Source 1 : 350 fichiers depuis le dataset CIC-EvasivePDF2022
python3 -m scripts.validation.prepare_corpus \
    --source /home/tisser_f/datasets/cic_pdf \
    --count 350 --label malicious \
    --output scripts/validation/real_corpus --seed 42

# Source 2 : 100 fichiers depuis MalwareBazaar (s'ajoutent au même malicious/)
python3 -m scripts.validation.prepare_corpus \
    --source /home/tisser_f/datasets/malwarebazaar_pdf \
    --count 100 --label malicious \
    --output scripts/validation/real_corpus --seed 42

# Source 3 : 50 benigns depuis arXiv
python3 -m scripts.validation.prepare_corpus \
    --source /home/tisser_f/datasets/arxiv_papers \
    --count 50 --label benign \
    --output scripts/validation/real_corpus --seed 42

# Lance l'analyse sur le corpus mixte
make sandbox-validate CORPUS=scripts/validation/real_corpus RUN_ID=runFinal REPS=2
```

---

## Dimensionnement MAX_INFLIGHT selon la RAM disponible

| RAM machine | MAX_INFLIGHT | Quota K8s | Temps ~4 000 jobs |
|---|---|---|---|
| 12 Gi | 7 | 20 | ~4h30 |
| 16 Gi | 15 | 30 | ~2h40 |
| 32 Gi | 25 | 50 | ~1h40 |
| 64 Gi+ | 40 | 100 | ~1h20 |

Chaque job sandbox demande **512 Mi RAM**. Le quota K8s doit être ≥ MAX_INFLIGHT + 10 (marge TTL).

Pour modifier le quota K8s :
```bash
kubectl edit resourcequota sandbox-namespace-quota -n sandbox
# spec.hard.count/jobs.batch: "20" → valeur souhaitée
```

---

## Cibles individuelles (contrôle fin)

Si tu veux orchestrer manuellement :

```bash
# Étape 1 — feed corpus dans Kafka + MinIO
make -f scripts/validation/Makefile feed CORPUS=<dir> RUN_ID=<id> REPS=2

# Étape 2 — collect les résultats sandbox_layer.result → DuckDB
make -f scripts/validation/Makefile collect RUN_ID=<id> DRAIN=1

# Étape 3 — génère le rapport Markdown
make -f scripts/validation/Makefile report REPORT_RUN_ID=<id>

# Reset offset du consumer group de validation (avant un nouveau run propre)
make -f scripts/validation/Makefile reset-offsets
```

---

## Architecture DNS (post-Option-B)

Le feeder qui tourne sur le **host** doit joindre :
- **MinIO via NodePort** pour l'upload (`MINIO_ENDPOINT = <node-ip>:<nodeport>`)
- **Kafka via NodePort** pour publier sur `file.requested` (`KAFKA_BOOTSTRAP = <node-ip>:32092`)

Le **Job in-cluster** doit joindre :
- **MinIO via DNS K8s** pour télécharger le sample (`minio.minio.svc.cluster.local:9000`)

C'est pour ça que le feeder utilise **2 endpoints distincts** :
- `MINIO_ENDPOINT` — pour son upload depuis le host
- `MINIO_PRESIGN_ENDPOINT` — pour générer l'URL que le Job consommera (DNS in-cluster)

Le `Makefile` les pose correctement automatiquement.

---

## Interprétation des résultats

### Section A — Déterminisme

| Résultat | Interprétation |
|---|---|
| >95% stables (Δ < 0.05) | ✅ Sandbox déterministe |
| 70–95% stables | ⚠️ Instabilité partielle — vérifier timing strace / ASLR |
| <70% stables | ❌ Non déterministe — blocker avant de lancer la section C |

### Section B — Distribution

Histogramme sain = distribution **bimodale** : cluster bas benign (<0.15) + cluster haut malicious (>0.40).
Si tout sort à 0.0 ou tout sort à 1.0 → le scoring est cassé.

### Section C — Justesse (verdict 3 bandes)

Le sandbox est un **tie-breaker** : il ne classe `malicious` qu'avec un signal fort,
`benign` qu'en l'absence de signal, et escalade l'ambigu au LLM via `needs_more_context`.
La matrice reflète ces 3 bandes (alignées sur `run_pdf_analysis._verdict_band`) :

```
benign  <  0.04  ≤  needs_more_context  <  0.15  ≤  malicious
```

| Métrique | Sens | Cible v1 |
|---|---|---|
| Precision confiante | quand il dit *malicious*, a-t-il raison | > 0.90 |
| Recall confiant | malicious classés *malicious* direct | indicatif |
| Recall avec escalade | malicious confirmés **ou** escaladés (jamais lavés) | > 0.95 |
| Ratés | malicious lavés en benign | **0** (seul vrai échec sécu) |

---

## Variables Makefile

| Variable | Défaut | Usage |
|---|---|---|
| `RUN_ID` | `validation_<timestamp>` | Identifiant de campagne |
| `REPS` | `1` | Répétitions par fichier (`REPS=2` pour le test déterminisme) |
| `CORPUS` | `scripts/validation/real_corpus` | Racine du corpus (canonique — samples gitignorés) |
| `MAX_INFLIGHT` | `15` | Plafond de jobs K3s simultanés |
| `RATE` | _(illimité)_ | Débit max msg/s |
| `IDLE_TIMEOUT` | `300` | Secondes d'inactivité avant drain auto |
| `REPORT_RUN_ID` | _(tous les runs)_ | Filtrer le rapport sur un run |
| `THRESHOLD` | `0.15` | Seuil bande **malicious** (section C) |
| `SUSPICIOUS_THRESHOLD` | `0.04` | Seuil bande **needs_more_context** (section C) |

---

## Idempotence — comportement en cas de crash

| Situation | Comportement au re-run |
|---|---|
| Crash feeder | Skip les `(run_id, sha256, rep)` déjà en DB — reprend où il s'est arrêté |
| Crash validator | Reprend depuis le dernier offset Kafka committé (group_id stable) |
| Job K3s timeout | Compté dans les erreurs du rapport, score = null |
| Quota K8s dépassé | Retry 3× (10s/20s/40s) puis publie une erreur sur Kafka — job jamais perdu silencieusement |
| Double `file.requested` | Impossible : `already_sent()` vérifie la DB avant chaque `send` |
| Fichier déjà dans MinIO | `stat_object()` avant `fput_object()` — upload ignoré |
