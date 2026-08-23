from backend.services.job_owner import JobOwnerRegistry


class TestJobOwnerRegistry:
    """Tests for the job ownership registry."""

    def test_owner_is_returned_for_a_claimed_job(self) -> None:
        """A claimed job resolves to the tenant that submitted it."""
        registry = JobOwnerRegistry(900)
        registry.register("job-1", "tenant-a")

        assert registry.owner("job-1") == "tenant-a"

    def test_unknown_job_has_no_owner(self) -> None:
        """An unclaimed job resolves to None, which no tenant_id can equal."""
        assert JobOwnerRegistry(900).owner("never-submitted") is None

    def test_claims_do_not_leak_between_tenants(self) -> None:
        """Two tenants claiming different jobs keep their own."""
        registry = JobOwnerRegistry(900)
        registry.register("job-a", "tenant-a")
        registry.register("job-b", "tenant-b")

        assert registry.owner("job-a") == "tenant-a"
        assert registry.owner("job-b") == "tenant-b"

    def test_expired_claim_is_dropped(self) -> None:
        """An expired claim stops resolving, so the registry cannot grow forever."""
        registry = JobOwnerRegistry(0)
        registry.register("job-1", "tenant-a")

        assert registry.owner("job-1") is None

    def test_expired_entries_are_purged_on_register(self) -> None:
        """Registering evicts stale claims rather than accumulating them."""
        registry = JobOwnerRegistry(0)
        registry.register("stale", "tenant-a")
        registry.register("fresh", "tenant-b")

        assert registry._owners.keys() == {"fresh"}
