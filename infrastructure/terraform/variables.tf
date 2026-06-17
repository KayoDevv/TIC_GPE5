variable "kubeconfig_path" {
  description = "Path to the k3s kubeconfig (see make setup-kubeconfig)."
  type        = string
  default     = "~/.kube/config"
}

variable "kafka_chart_version" {
  description = "Bitnami Kafka chart version (mirrors Makefile KAFKA_CHART_VERSION)."
  type        = string
  default     = "31.0.0"
}

variable "keda_chart_version" {
  description = "KEDA chart version — must match the deployed release (helm list -n keda) so plan/apply does not up/downgrade it. Currently 2.20.0 on the cluster."
  type        = string
  default     = "2.20.0"
}

variable "kafka_dev_external_access" {
  description = "Layer kafka/values-dev.yaml (NodePort externalAccess) on top of prod values. Flipped by make dev-expose/dev-teardown; keep false in prod."
  type        = bool
  default     = false
}
