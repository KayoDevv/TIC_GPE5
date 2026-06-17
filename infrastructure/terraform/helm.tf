# Engine — single owner: Terraform (T3). KEDA + Kafka Helm releases.
# MinIO is deliberately NOT here: it stays kustomize/Make-owned (it hosts the TF
# state backend — TF must not own the store of its own state — and a hand-written
# StatefulSet cannot be imported to a 0-diff plan). See docs/terraform-frontier.md.
#
# Kafka topics: the 6 topics are provisioned BY the Bitnami chart (values.yaml
# `provisioning.topics`). No separate topic resource, no mongey/kafka provider.

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

  # Prod values always; dev externalAccess (NodePort) layered ON TOP only when
  # var.kafka_dev_external_access is set. `make dev-expose` flips that variable
  # instead of running `helm upgrade` behind Terraform's back (single owner).
  values = concat(
    [file("${path.module}/../k8s-manifests/applications/kafka/values.yaml")],
    var.kafka_dev_external_access ? [file("${path.module}/../k8s-manifests/applications/kafka/values-dev.yaml")] : []
  )

  depends_on = [kubernetes_namespace.charon]
}
