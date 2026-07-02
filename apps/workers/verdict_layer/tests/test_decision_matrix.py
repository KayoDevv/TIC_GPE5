from verdict_layer.decision_matrix import (
    SANDBOX_ERROR_EXPLANATION,
    SANDBOX_MALICIOUS_EXPLANATION,
    JobState,
    decide,
)


class TestEarlyExitMlScore:
    """Rule 1: ml_score > 90 -> immediate blocked (highest priority)."""

    def test_ml_score_above_threshold_blocks(self) -> None:
        state = JobState(ml_score=95)
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "blocked"

    def test_ml_score_exactly_threshold_does_not_block(self) -> None:
        """Strictly greater than 90 — exactly 90 is not enough on its own."""
        state = JobState(ml_score=90, llm_is_malicious=False, sandbox_received=True)
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "allowed"

    def test_ml_score_above_threshold_wins_over_clean_llm(self) -> None:
        """Even if the LLM says clean, a high ML score blocks."""
        state = JobState(ml_score=99, llm_is_malicious=False)
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "blocked"


class TestLlmMalicious:
    """Rule 2: llm.is_malicious == true -> blocked."""

    def test_llm_malicious_blocks(self) -> None:
        state = JobState(ml_score=20, sandbox_received=True, llm_is_malicious=True)
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "blocked"

    def test_llm_malicious_includes_explanation(self) -> None:
        state = JobState(
            ml_score=20,
            sandbox_received=True,
            llm_is_malicious=True,
            llm_explanation="The file opened PowerShell and contacted an external host.",
        )
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert (
            result.user_explanation == "The file opened PowerShell and contacted an external host."
        )


class TestSandboxTimeout:
    """Rule 3: sandbox timeout -> warning or blocked per tenant tolerance."""

    def test_timeout_default_warning(self) -> None:
        state = JobState(ml_score=20, sandbox_timeout=True)
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "warning"

    def test_timeout_default_blocked(self) -> None:
        state = JobState(ml_score=20, sandbox_timeout=True)
        result = decide(state, ml_block_threshold=90, timeout_default="blocked")
        assert result.final_decision == "blocked"

    def test_high_ml_score_wins_over_timeout(self) -> None:
        """ML early-exit has priority even if sandbox timed out."""
        state = JobState(ml_score=99, sandbox_timeout=True)
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "blocked"

    def test_llm_malicious_wins_over_timeout(self) -> None:
        """If the LLM ran and flagged malicious, that blocks over a timeout default."""
        state = JobState(ml_score=20, sandbox_timeout=True, llm_is_malicious=True)
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "blocked"


class TestAllowed:
    """Default: everything received, nothing malicious -> allowed."""

    def test_all_clean_allows(self) -> None:
        state = JobState(
            ml_score=10,
            sandbox_received=True,
            llm_is_malicious=False,
        )
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "allowed"


class TestSandboxVerdict:
    """A terminal sandbox verdict resolves the job even when the LLM never ran."""

    def test_sandbox_malicious_blocks(self) -> None:
        state = JobState(ml_score=20, sandbox_received=True, sandbox_verdict="malicious")
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "blocked"
        assert result.user_explanation == SANDBOX_MALICIOUS_EXPLANATION

    def test_sandbox_benign_allows(self) -> None:
        state = JobState(ml_score=20, sandbox_received=True, sandbox_verdict="benign")
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "allowed"

    def test_sandbox_error_warns(self) -> None:
        state = JobState(ml_score=20, sandbox_received=True, sandbox_verdict="error")
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "warning"
        assert result.user_explanation == SANDBOX_ERROR_EXPLANATION

    def test_ml_critical_wins_over_sandbox_malicious(self) -> None:
        state = JobState(ml_score=99, sandbox_received=True, sandbox_verdict="malicious")
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.user_explanation != SANDBOX_MALICIOUS_EXPLANATION

    def test_timeout_wins_over_sandbox_error(self) -> None:
        # A job that both errored and timed out should read as a timeout.
        state = JobState(
            ml_score=20, sandbox_received=True, sandbox_timeout=True, sandbox_verdict="error"
        )
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.final_decision == "warning"
        assert result.user_explanation != SANDBOX_ERROR_EXPLANATION


class TestTechnicalSummary:
    """The verdict must carry a technical summary of the collected data."""

    def test_summary_reflects_state(self) -> None:
        state = JobState(
            ml_score=10,
            sandbox_received=True,
            sandbox_timeout=False,
            llm_is_malicious=False,
        )
        result = decide(state, ml_block_threshold=90, timeout_default="warning")
        assert result.technical_summary is not None
        assert result.technical_summary["ml_layer_score"] == 10
        assert result.technical_summary["llm_layer_malicious"] is False
        assert result.technical_summary["sandbox_layer_timeout"] is False
