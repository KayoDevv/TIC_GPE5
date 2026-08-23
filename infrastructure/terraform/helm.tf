# Engine — KEDA + Kafka Helm releases. MinIO is deliberately NOT here: it hosts
# the TF state backend (TF can't own the store of its own state) and a hand-written
# StatefulSet won't import to a 0-diff plan — it stays kustomize/Make-owned.
# Kafka topics are provisioned by the Bitnami chart (values.yaml), no extra provider.

resource "helm_release" "keda" {
  name       = "keda"
  repository = "https://kedacore.github.io/charts"
  chart      = "keda"
  version    = var.keda_chart_version
  namespace  = "keda"
  # The keda namespace is NOT TF-managed (not in namespaces.tf) — let Helm own it.
  create_namespace = true
  wait             = true
  timeout          = 300

  values = [file("${path.module}/../k8s-manifests/applications/keda/values.yaml")]
}

resource "helm_release" "kafka" {
  name       = "kafka"
  repository = "https://charts.bitnami.com/bitnami"
  chart      = "kafka"
  version    = var.kafka_chart_version
  namespace  = "kafka"
  # kafka namespace is TF-owned (namespaces.tf) → do not let Helm create it.
  create_namespace = false
  wait             = true
  timeout          = 600

  # Prod values always; dev NodePort layered on top via var.kafka_dev_external_access
  # (make dev-expose flips it instead of a separate helm upgrade — single owner).
  values = concat(
    [file("${path.module}/../k8s-manifests/applications/kafka/values.yaml")],
    var.kafka_dev_external_access ? [file("${path.module}/../k8s-manifests/applications/kafka/values-dev.yaml")] : []
  )

  depends_on = [kubernetes_namespace.charon]
}
