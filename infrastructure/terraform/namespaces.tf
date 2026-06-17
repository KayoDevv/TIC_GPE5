# Charon cluster namespaces — single owner: Terraform.
#
# Labels reproduce the original kustomize manifests EXACTLY
# (applications/*/namespace.yaml) so that `terraform plan` shows 0 changes
# after import. Once imported AND the empty plan is verified, the namespace.yaml
# files are removed from the kustomize bases (anti-double-ownership).
#
# NOTE: kafka/minio only carry `name: <ns>` (referenced by the netpols via
# namespaceSelector). sandbox/sinkhole carry part-of=charon + PSA=privileged
# (INTENTIONAL — the Jobs add CAP_SYS_PTRACE, outside the baseline/restricted
# allow-list; the real hardening lives in the pods' securityContext).
#
# Import note: K8s auto-adds the `kubernetes.io/metadata.name` label, which the
# hashicorp/kubernetes provider ignores on read (>= v2.18) — so it is NOT
# declared here. If `plan` still reports a diff after import, see
# docs/terraform-frontier.md (verification step) to align with reality.

locals {
  # PSA labels shared by sandbox + sinkhole (privileged is INTENTIONAL).
  psa_privileged = {
    "app.kubernetes.io/part-of"          = "charon"
    "pod-security.kubernetes.io/enforce" = "privileged"
    "pod-security.kubernetes.io/audit"   = "privileged"
    "pod-security.kubernetes.io/warn"    = "privileged"
  }

  namespaces = {
    kafka    = { "name" = "kafka" }
    minio    = { "name" = "minio" }
    sandbox  = local.psa_privileged
    sinkhole = local.psa_privileged
  }
}

resource "kubernetes_namespace" "charon" {
  for_each = local.namespaces

  metadata {
    name   = each.key
    labels = each.value
  }
}
