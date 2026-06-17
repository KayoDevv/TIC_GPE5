# Make / Terraform boundary

The Charon cluster used to be deployed 100% imperatively (Make + kubectl + helm
+ kustomize). Terraform now takes over the declarative layer incrementally.
**Golden rule: one K8s object = one owner.** Never Terraform *and*
kustomize/kubectl on the same object (drift/conflicts otherwise).

## Who owns what (the ferry metaphor)

| Layer | Owner | Why |
|-------|-------|-----|
| **Hull**: host/OS, k3s, CNI binary, `runsc`, image build/import, **TF driver** | **Makefile** | Exists before the API server; not a K8s object |
| **Compartments**: namespaces, RBAC, NetworkPolicies, RuntimeClass, gvisor VAP | **Terraform** | Pure, stable, declarative K8s objects |
| **Engine**: Helm KEDA+Kafka, topics, MinIO StatefulSet | **Terraform** | Infra services, a single `plan` |
| **Cargo**: workers (consumer/watcher/job), sinkhole, dev overlay | **Kustomize / Make** | Coupled to image build/import (T4 deferred) |

## Phasing

- **T1 — Foundation + Namespaces** ← *this slice*
- **T2 — Compartments**: RBAC, NetworkPolicy, RuntimeClass, gvisor VAP
- **T3 — Engine**: Helm KEDA/Kafka, topics, MinIO
- **T4 — Cargo**: stays kustomize/Make (out of scope)

---

## T1 — Foundation: state backend + namespaces

### Files
- `infrastructure/terraform/main.tf` — `kubernetes`/`helm` providers + `s3`
  backend on MinIO (NodePort 32090, all AWS-specific checks skipped).
- `infrastructure/terraform/namespaces.tf` — `kafka`/`minio`/`sandbox`/`sinkhole`
  (labels reproduced exactly from the former `namespace.yaml` files).
- Kustomize bases: `- namespace.yaml` removed from the 4 `kustomization.yaml`
  files; the `namespace.yaml` files deleted (PSA rationale kept in `namespaces.tf`).
- `Makefile`: targets `tf-bootstrap-state`, `tf-init`, `tf-plan`, `tf-apply`,
  `tf-import-namespaces`.

### Chicken / egg (backend inside MinIO)
The TF state lives in MinIO, but MinIO and its namespaces already exist
(historically deployed by kustomize). On the **existing cluster** (the real
case) the order is therefore simple: MinIO is already running -> create the
state bucket -> import. *(MinIO stays kustomize-owned until T3; only its
namespace moves to TF here, by import.)*

### VM runbook (gate before merge)

> Prerequisites: MinIO running (`make deploy-minio`), dev NodePort exposed
> (`make dev-expose` -> 32090), `mc` + `terraform` installed.

```bash
# 1. State bucket (one-shot, idempotent)
make tf-bootstrap-state

# 2. Init backend
make tf-init

# 3. Import the 4 existing namespaces BEFORE any apply
make tf-import-namespaces

# 4. GATE: plan MUST show "No changes" (0 add / 0 change / 0 destroy)
make tf-plan
```

**If `tf-plan` does not show 0 changes**: a label differs from reality. Most
likely cause = the auto `kubernetes.io/metadata.name` label (already handled —
the provider ignores it on read) or a label added outside the repo. Align
`namespaces.tf` with reality (`kubectl get ns <n> -o yaml`) until the plan is
empty. **Do not merge until the plan is empty** — that is the proof the import
reflects the existing state (nothing recreated/destroyed).

### Anti-double-ownership (post-import check)
```bash
# kustomize must NO LONGER recreate the namespaces
kubectl apply -k infrastructure/k8s-manifests/applications/sandbox/ --dry-run=server
# -> no Namespace object in the diff
```

### Fresh cluster (note)
On a from-scratch cluster the order becomes: `deploy-minio` (kustomize, creates
the minio ns + MinIO) -> `tf-bootstrap-state` -> `tf-init` -> `tf-apply`
(creates the remaining namespaces). The initial `minio` ns is then created by
kustomize and imported afterwards. Industrialising this sequencing is a
post-T1 refinement (the real case here is the existing cluster).

---

## T2 — Compartments: RBAC + NetworkPolicy + RuntimeClass

### Files
- `infrastructure/terraform/rbac.tf` — ServiceAccounts (sandbox-consumer /
  -analysis / -watcher), Role `sandbox-job-dispatcher`, its RoleBinding.
- `infrastructure/terraform/networkpolicy.tf` — the 7 NetworkPolicies (4 sandbox
  + 2 kafka + 1 sinkhole).
- `infrastructure/terraform/runtimeclass.tf` — the `gvisor` RuntimeClass.
- Kustomize: `rbac.yaml` + the 3 `networkpolicy.yaml` deleted; the emptied
  `kafka/kustomization.yaml` deleted; `make setup-kafka` no longer applies it.
- `Makefile`: `make install-gvisor` no longer applies the RuntimeClass (host
  layer only); new `tf-import-compartments` target.

### Stays Make-owned (deliberate)
- **gvisor VAP** (`require-gvisor-vap.yaml`, `make enforce-gvisor`): the
  hashicorp/kubernetes provider has no typed ValidatingAdmissionPolicy resource,
  and `kubernetes_manifest` cannot cleanly import an existing fail-closed object
  without a brief enforcement gap. Kept in Make until a typed resource exists.
- **`consumer-apiserver-egress`** (`make netpol-apiserver`): host-networked
  apiserver matched by the node IP (host-specific, discovered at deploy time).
  The only host-specific netpol.
- **gvisor host layer** (`runsc` binary + containerd runtime, `make
  install-gvisor`): not K8s objects; must exist on the node before the
  RuntimeClass handler can be scheduled.

### VM runbook (gate before merge)

> Prerequisite: T1 applied (namespaces owned by TF, state backend live).

```bash
# 1. Import the existing compartment objects BEFORE any apply
make tf-import-compartments

# 2. GATE: plan MUST show "No changes"
make tf-plan
```

If `tf-plan` is not empty, align the `.tf` with reality
(`kubectl get <kind> <name> -n <ns> -o yaml`) until empty. **Do not merge until
the plan is empty.** Then verify kustomize/Make no longer recreate the migrated
objects:
```bash
kubectl apply -k infrastructure/k8s-manifests/applications/sandbox/ --dry-run=server
# -> no ServiceAccount / Role / RoleBinding / NetworkPolicy in the diff
```

---

## T3 — Engine: Helm KEDA + Kafka

### Files
- `infrastructure/terraform/helm.tf` — `helm_release` for KEDA and Kafka
  (Bitnami v31.0.0). The 6 Kafka topics are provisioned BY the chart
  (`values.yaml` `provisioning.topics`) — no separate topic resource, no
  `mongey/kafka` provider.
- `variables.tf` — `kafka_chart_version`, `keda_chart_version`,
  `kafka_dev_external_access`.
- `Makefile`: `setup-keda`/`setup-kafka` are now DEPRECATED no-op shims;
  `deploy-infra` brings up MinIO then points at the tf-* flow; `dev-expose`/
  `dev-teardown` flip `kafka_dev_external_access` via `terraform apply` instead
  of a parallel `helm upgrade`; `tf-import-engine` target added.

### Stays Make/kustomize-owned (deliberate)
- **MinIO** (StatefulSet + Services + Secret + bucket-init): it hosts the TF
  state backend (TF owning the store of its own state is circular and risky),
  and a hand-written StatefulSet cannot be imported to a 0-diff plan. Remains
  kustomize/Make-owned (`make deploy-minio`).
- **KEDA ScaledObject** (sandbox): cargo (scales the consumer), stays in the
  sandbox kustomization.

### VM runbook (gate before merge)

> Prerequisite: T1 + T2 applied. KEDA + Kafka already running (helm).

```bash
# 1. Align KEDA version to the deployed release (so the plan can be empty)
helm list -n keda          # read the chart version, e.g. keda-2.15.1 -> 2.15.1
#   set var.keda_chart_version accordingly (terraform.tfvars or -var)

# 2. Import the existing Helm releases BEFORE any apply
make tf-import-engine

# 3. GATE: plan MUST show "No changes"
make tf-plan
```

The Helm provider can surface diffs on `values`/`version` after import. Align
`kafka_chart_version` / `keda_chart_version` and the values files to the
deployed releases until `tf-plan` is empty. **Do not merge until empty.**

### After the whole stack is applied
`make tf-apply` reconciles namespaces + compartments + engine in one plan.
`make dev-expose` / `dev-teardown` toggle the Kafka NodePort through Terraform.
