# Sandbox RBAC — single owner: Terraform (T2). Migrated from
# k8s-manifests/applications/sandbox/rbac.yaml (removed from kustomize).
#
# Least-privilege split:
#   - sandbox-consumer  : may CREATE Jobs + read pods/logs (dispatcher).
#   - sandbox-analysis  : detonation Jobs, NO API rights (token not mounted).
#   - sandbox-watcher   : minio-watcher, NO API rights (token not mounted).

resource "kubernetes_service_account_v1" "consumer" {
  metadata {
    name      = "sandbox-consumer"
    namespace = "sandbox"
  }
}

# No K8s API rights: token explicitly not mounted (defence in depth — if the
# detonation/watcher pod is compromised it cannot talk to the API server).
resource "kubernetes_service_account_v1" "analysis" {
  metadata {
    name      = "sandbox-analysis"
    namespace = "sandbox"
  }
  automount_service_account_token = false
}

resource "kubernetes_service_account_v1" "watcher" {
  metadata {
    name      = "sandbox-watcher"
    namespace = "sandbox"
  }
  automount_service_account_token = false
}

# The consumer creates Jobs (one per sample). No delete verb: the Job's
# ownerReference handles GC via TTLAfterFinished.
resource "kubernetes_role_v1" "job_dispatcher" {
  metadata {
    name      = "sandbox-job-dispatcher"
    namespace = "sandbox"
  }
  rule {
    api_groups = ["batch"]
    resources  = ["jobs"]
    verbs      = ["create", "get", "list", "watch"]
  }
  rule {
    api_groups = [""]
    resources  = ["pods", "pods/log"]
    verbs      = ["get", "list", "watch"]
  }
}

resource "kubernetes_role_binding_v1" "consumer_can_dispatch" {
  metadata {
    name      = "sandbox-consumer-can-dispatch"
    namespace = "sandbox"
  }
  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.job_dispatcher.metadata[0].name
  }
  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.consumer.metadata[0].name
    namespace = "sandbox"
  }
}
