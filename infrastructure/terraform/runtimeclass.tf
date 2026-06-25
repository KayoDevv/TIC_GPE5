# gVisor RuntimeClass (the K8s object only). The host layer — runsc binary,
# containerd shim, runsc runtime in the K3s config — stays in `make install-gvisor`.
resource "kubernetes_runtime_class_v1" "gvisor" {
  metadata {
    name = "gvisor"
  }
  handler = "runsc"
}
