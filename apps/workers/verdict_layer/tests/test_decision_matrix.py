from verdict_layer.decision_matrix import (
    ML_ABSTAINED_EXPLANATION,
    ML_BLOCKED_EXPLANATION,
    ML_DISPUTED_EXPLANATION,
    SANDBOX_ERROR_EXPLANATION,
    SANDBOX_MALICIOUS_EXPLANATION,
    SANDBOX_TIMEOUT_EXPLANATION,
    JobState,
    VerdictDecision,
    decide,
)

_BLOCK_THRESHOLD = 90


def _decide(
    state: JobState,
    *,
    timeout_default: str = "warning",
    ml_abstain_verdict: str = "warning",
) -> VerdictDecision:
    return decide(
        state,
        ml_block_threshold=_BLOCK_THRESHOLD,
        ml_solo_block_threshold=98,
        timeout_default=timeout_default,
        ml_abstain_verdict=ml_abstain_verdict,
    )


class TestMlCriticalRequiresCorroboration:
    def test_ml_critical_blocks_when_sandbox_malicious(self) -> None:
        state = JobState(ml_score=95, sandbox_received=True, sandbox_verdict="malicious")
        result = _decide(state)
        assert result.final_decision == "blocked"

    def test_ml_critical_downgrades_to_warning_when_sandbox_benign(self) -> None:
        state = JobState(ml_score=99, sandbox_received=True, sandbox_verdict="benign")
        result = _decide(state)
        assert result.final_decision == "warning"
        assert result.user_explanation == ML_DISPUTED_EXPLANATION

    def test_ml_critical_disputed_by_clean_llm(self) -> None:
        state = JobState(
            ml_score=99,
            sandbox_received=True,
            sandbox_verdict="needs_more_context",
            llm_is_malicious=False,
        )
        result = _decide(state)
        assert result.final_decision == "warning"

    def test_ml_exactly_threshold_does_not_trigger(self) -> None:
        state = JobState(ml_score=90, llm_is_malicious=False, sandbox_received=True)
        result = _decide(state)
        assert result.final_decision == "allowed"


class TestLlmMalicious:
    """Rule 2: llm.is_malicious == true -> blocked."""

    def test_llm_malicious_blocks(self) -> None:
        state = JobState(ml_score=20, sandbox_received=True, llm_is_malicious=True)
        result = _decide(state)
        assert result.final_decision == "blocked"

    def test_llm_malicious_includes_explanation(self) -> None:
        state = JobState(
            ml_score=20,
            sandbox_received=True,
            llm_is_malicious=True,
            llm_explanation="The file opened PowerShell and contacted an external host.",
        )
        result = _decide(state)
        assert (
            result.user_explanation == "The file opened PowerShell and contacted an external host."
        )


class TestSandboxTimeout:
    """Rule 3: sandbox timeout -> warning or blocked per tenant tolerance."""

    def test_timeout_default_warning(self) -> None:
        state = JobState(ml_score=20, sandbox_timeout=True)
        result = _decide(state)
        assert result.final_decision == "warning"

    def test_timeout_default_blocked(self) -> None:
        state = JobState(ml_score=20, sandbox_timeout=True)
        result = _decide(state, timeout_default="blocked")
        assert result.final_decision == "blocked"

    def test_critical_ml_score_does_not_block_a_timeout(self) -> None:
        state = JobState(ml_score=97, sandbox_timeout=True)
        result = _decide(state)
        assert result.final_decision == "warning"
        assert result.user_explanation == SANDBOX_TIMEOUT_EXPLANATION

    def test_near_certain_ml_score_blocks_a_timeout(self) -> None:
        state = JobState(ml_score=99, sandbox_timeout=True)
        result = _decide(state)
        assert result.final_decision == "blocked"
        assert result.user_explanation == ML_BLOCKED_EXPLANATION

    def test_high_ml_score_follows_blocking_timeout_policy(self) -> None:
        state = JobState(ml_score=99, sandbox_timeout=True)
        result = _decide(state, timeout_default="blocked")
        assert result.final_decision == "blocked"

    def test_llm_malicious_wins_over_timeout(self) -> None:
        """If the LLM ran and flagged malicious, that blocks over a timeout default."""
        state = JobState(ml_score=20, sandbox_timeout=True, llm_is_malicious=True)
        result = _decide(state)
        assert result.final_decision == "blocked"


class TestAllowed:
    """Default: everything received, nothing malicious -> allowed."""

    def test_all_clean_allows(self) -> None:
        state = JobState(
            ml_score=10,
            sandbox_received=True,
            llm_is_malicious=False,
        )
        result = _decide(state)
        assert result.final_decision == "allowed"


class TestSandboxVerdict:
    """A terminal sandbox verdict resolves the job even when the LLM never ran."""

    def test_sandbox_malicious_blocks(self) -> None:
        state = JobState(ml_score=20, sandbox_received=True, sandbox_verdict="malicious")
        result = _decide(state)
        assert result.final_decision == "blocked"
        assert result.user_explanation == SANDBOX_MALICIOUS_EXPLANATION

    def test_sandbox_benign_allows(self) -> None:
        state = JobState(ml_score=20, sandbox_received=True, sandbox_verdict="benign")
        result = _decide(state)
        assert result.final_decision == "allowed"

    def test_sandbox_error_warns(self) -> None:
        state = JobState(ml_score=20, sandbox_received=True, sandbox_verdict="error")
        result = _decide(state)
        assert result.final_decision == "warning"
        assert result.user_explanation == SANDBOX_ERROR_EXPLANATION

    def test_sandbox_explanation_kept_when_ml_critical(self) -> None:
        state = JobState(ml_score=99, sandbox_received=True, sandbox_verdict="malicious")
        result = _decide(state)
        assert result.final_decision == "blocked"
        assert result.user_explanation == SANDBOX_MALICIOUS_EXPLANATION

    def test_ml_critical_does_not_block_a_sandbox_error(self) -> None:
        state = JobState(ml_score=98, sandbox_received=True, sandbox_verdict="error")
        result = _decide(state)
        assert result.final_decision == "warning"
        assert result.user_explanation == SANDBOX_ERROR_EXPLANATION

    def test_near_certain_ml_blocks_a_sandbox_error(self) -> None:
        state = JobState(ml_score=99, sandbox_received=True, sandbox_verdict="error")
        result = _decide(state)
        assert result.final_decision == "blocked"

    def test_near_certain_ml_never_overrides_a_clean_sandbox(self) -> None:
        state = JobState(ml_score=100, sandbox_received=True, sandbox_verdict="benign")
        result = _decide(state)
        assert result.final_decision == "warning"
        assert result.user_explanation == ML_DISPUTED_EXPLANATION

    def test_timeout_wins_over_sandbox_error(self) -> None:
        # A job that both errored and timed out should read as a timeout.
        state = JobState(
            ml_score=20, sandbox_received=True, sandbox_timeout=True, sandbox_verdict="error"
        )
        result = _decide(state)
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
        result = _decide(state)
        assert result.technical_summary is not None
        assert result.technical_summary["ml_layer_score"] == 10
        assert result.technical_summary["llm_layer_malicious"] is False
        assert result.technical_summary["sandbox_layer_timeout"] is False


class TestMlAbstention:
    def test_abstention_downgrades_an_otherwise_allowed_verdict(self) -> None:
        state = JobState(
            ml_score=0,
            ml_status="analysis_failed",
            sandbox_received=True,
            sandbox_verdict="benign",
        )

        result = _decide(state)

        assert result.final_decision == "warning"
        assert result.user_explanation == ML_ABSTAINED_EXPLANATION

    def test_abstention_does_not_soften_a_blocked_verdict(self) -> None:
        state = JobState(
            ml_score=0,
            ml_status="unsupported_file_type",
            sandbox_received=True,
            sandbox_verdict="malicious",
        )

        result = _decide(state)

        assert result.final_decision == "blocked"

    def test_abstention_score_is_never_treated_as_critical(self) -> None:
        state = JobState(
            ml_score=99,
            ml_status="analysis_failed",
            sandbox_received=True,
            sandbox_verdict="benign",
        )

        result = _decide(state)

        assert result.final_decision == "warning"
        assert result.user_explanation == ML_ABSTAINED_EXPLANATION

    def test_abstention_score_is_withheld_from_the_technical_summary(self) -> None:
        state = JobState(
            ml_score=99,
            ml_status="analysis_failed",
            sandbox_received=True,
            sandbox_verdict="benign",
        )

        result = _decide(state)

        assert result.technical_summary is not None
        assert result.technical_summary["ml_layer_score"] is None
        assert result.technical_summary["ml_layer_status"] == "analysis_failed"

    def test_tenant_may_keep_allowing_on_abstention(self) -> None:
        state = JobState(
            ml_score=0,
            ml_status="analysis_failed",
            sandbox_received=True,
            sandbox_verdict="benign",
        )

        result = _decide(state, ml_abstain_verdict="allowed")

        assert result.final_decision == "allowed"

    def test_completed_analysis_is_not_an_abstention(self) -> None:
        state = JobState(
            ml_score=10,
            ml_status="completed",
            sandbox_received=True,
            sandbox_verdict="benign",
        )

        result = _decide(state)

        assert result.final_decision == "allowed"
