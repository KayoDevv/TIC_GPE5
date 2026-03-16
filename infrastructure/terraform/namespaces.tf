resource "kubernetes_namespace" "all" {
  for_each = toset(var.namespaces)

  metadata {
    name = each.value
    labels = {
      managed-by = "terraform"
      project    = var.project_name
    }
  }
}