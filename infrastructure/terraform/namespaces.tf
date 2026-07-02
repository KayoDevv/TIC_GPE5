# Charon cluster namespaces — single owner: Terraform. Labels mirror the original
# kustomize manifests so a post-import `terraform plan` is empty.
#
# kafka/minio carry only `name: <ns>` (netpol namespaceSelector). sandbox/sinkhole
# carry PSA=privileged INTENTIONALLY — the analysis Jobs add CAP_SYS_PTRACE (outside
# the baseline/restricted allow-list); real hardening is in the pod securityContext.
# The auto `kubernetes.io/metadata.name` label is omitted (provider ignores it on read).

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
    # Core analysis workers (backend, ml, verdict, llm) + redis. Restricted PSA
    # is fine — every pod runs non-root, drops all caps, seccomp RuntimeDefault.
    pipeline = { "name" = "pipeline" }
  }
}

resource "kubernetes_namespace" "charon" {
  for_each = local.namespaces

  metadata {
    name   = each.key
    labels = each.value
  }
}
