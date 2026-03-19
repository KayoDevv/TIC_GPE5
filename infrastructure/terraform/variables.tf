variable "namespaces" {
  description = "Liste des namespaces à créer"
  type        = list(string)
}

variable "project_name" {
  description = "Nom du projet pour les labels"
  type        = string
  default     = "etna-project"
}