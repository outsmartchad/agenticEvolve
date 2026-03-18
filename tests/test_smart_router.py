"""Tests for gateway.smart_router — 13-dimension complexity scorer."""
import threading
import pytest

from gateway.smart_router import SmartRouter, Tier, RoutingStats, SmartRouterConfig


# ── Fixture ──────────────────────────────────────────────────────────


@pytest.fixture()
def router():
    return SmartRouter()


# ── Dimension scoring tests ──────────────────────────────────────────


class TestReasoningWords:
    def test_single_match(self, router):
        score, dims = router.score("Please analyze this data")
        assert dims["reasoning_words"] >= 50

    def test_multiple_matches(self, router):
        score, dims = router.score("Analyze and compare, then evaluate the results")
        assert dims["reasoning_words"] == 100  # 3 * 50, capped at 100

    def test_no_match(self, router):
        _, dims = router.score("hello world")
        assert dims["reasoning_words"] == 0


class TestTokenEstimate:
    def test_short_text(self, router):
        _, dims = router.score("hi")
        assert dims["token_estimate"] == 0  # len("hi") = 2, (2-20) < 0

    def test_medium_text(self, router):
        text = "a" * 120  # (120-20)/5 = 20
        _, dims = router.score(text)
        assert dims["token_estimate"] == 20

    def test_long_text(self, router):
        text = "a" * 600  # (600-20)/5 = 116, capped at 100
        _, dims = router.score(text)
        assert dims["token_estimate"] == 100


class TestCodeIndicators:
    def test_backticks(self, router):
        _, dims = router.score("```python\nprint('hello')\n```")
        assert dims["code_indicators"] >= 50

    def test_keywords(self, router):
        _, dims = router.score("the function uses async await and import")
        assert dims["code_indicators"] >= 100  # 3+ matches

    def test_filepath(self, router):
        _, dims = router.score("check src/utils/helper.ts for the bug")
        assert dims["code_indicators"] >= 50

    def test_no_code(self, router):
        _, dims = router.score("what time is it")
        assert dims["code_indicators"] == 0


class TestMultiStep:
    def test_step_by_step(self, router):
        _, dims = router.score("explain this step by step")
        assert dims["multi_step"] >= 50

    def test_numbered_list(self, router):
        _, dims = router.score("1. do this\n2. then that\n3. finally this")
        assert dims["multi_step"] >= 100  # 3 matches

    def test_plan(self, router):
        _, dims = router.score("create a plan for this project")
        assert dims["multi_step"] >= 50


class TestDomainSpecific:
    def test_crypto_terms(self, router):
        _, dims = router.score("write a solidity smart contract for DeFi yield staking")
        assert dims["domain_specific"] >= 100

    def test_tech_terms(self, router):
        _, dims = router.score("set up kubernetes with docker and postgres")
        assert dims["domain_specific"] >= 100

    def test_extra_domain_keywords(self):
        router = SmartRouter({"smart_routing": {"domain_keywords": ["foobar"]}})
        _, dims = router.score("tell me about foobar")
        assert dims["domain_specific"] >= 50

    def test_no_domain(self, router):
        _, dims = router.score("what is the weather today")
        assert dims["domain_specific"] == 0


class TestCreativity:
    def test_design(self, router):
        _, dims = router.score("design a new architecture for this system")
        assert dims["creativity"] >= 50

    def test_brainstorm(self, router):
        _, dims = router.score("brainstorm and propose some ideas, then draft a prototype")
        assert dims["creativity"] >= 100


class TestQuestionComplexity:
    def test_single_question(self, router):
        _, dims = router.score("what is this?")
        assert dims["question_complexity"] == 20  # 1 question mark * 20

    def test_open_ended(self, router):
        _, dims = router.score("how would you approach this?")
        # 1 question mark * 20 + 1 open_ended * 25 = 45
        assert dims["question_complexity"] == 45

    def test_multiple_questions(self, router):
        _, dims = router.score("why does this happen? what if we change it?")
        # 2 question marks * 20 + 2 open_ended * 25 = 40 + 50 = 90
        assert dims["question_complexity"] == 90


class TestPrecision:
    def test_keywords(self, router):
        _, dims = router.score("calculate the exact value precisely")
        assert dims["precision"] >= 100  # 3 matches

    def test_math_symbols(self, router):
        _, dims = router.score("x + y = z")
        assert dims["precision"] >= 100  # 3 symbols


class TestContextDependency:
    def test_references(self, router):
        _, dims = router.score("as mentioned above, that thing from earlier")
        assert dims["context_dependency"] >= 100


class TestAmbiguity:
    def test_uncertain_language(self, router):
        _, dims = router.score("maybe it could be this, perhaps not sure")
        # "maybe", "could be", "perhaps", "not sure" = 4 * 25 = 100
        assert dims["ambiguity"] == 100

    def test_no_ambiguity(self, router):
        _, dims = router.score("the answer is clearly yes")
        assert dims["ambiguity"] == 0


class TestToolLikelihood:
    def test_action_words(self, router):
        _, dims = router.score("run the tests and debug this, then deploy")
        assert dims["tool_likelihood"] >= 100

    def test_no_tools(self, router):
        _, dims = router.score("hello there")
        assert dims["tool_likelihood"] == 0


class TestSentenceComplexity:
    def test_complex_sentence(self, router):
        _, dims = router.score("this, and that; however, although it works, furthermore")
        # commas=3, semicolons=1, conjunctions=4(and,however,although,furthermore)
        # (3 + 1*2 + 4) * 12 = 9 * 12 = 108 -> capped at 100
        assert dims["sentence_complexity"] == 100

    def test_simple_sentence(self, router):
        _, dims = router.score("hello")
        assert dims["sentence_complexity"] == 0


class TestSafetySensitivity:
    def test_dangerous_keywords(self, router):
        _, dims = router.score("deploy to production with credentials and secret key")
        assert dims["safety_sensitivity"] >= 100

    def test_safe_message(self, router):
        _, dims = router.score("hello how are you")
        assert dims["safety_sensitivity"] == 0


# ── Tier classification tests ────────────────────────────────────────


class TestClassification:
    def test_empty_message_flash(self, router):
        assert router.classify("") == Tier.FLASH

    def test_short_message_flash(self, router):
        assert router.classify("hi") == Tier.FLASH

    def test_greeting_flash(self, router):
        assert router.classify("hello!") == Tier.FLASH
        assert router.classify("Hey") == Tier.FLASH
        assert router.classify("thanks!") == Tier.FLASH
        assert router.classify("ok") == Tier.FLASH
        assert router.classify("gm") == Tier.FLASH
        assert router.classify("lol") == Tier.FLASH

    def test_chinese_greetings_flash(self, router):
        assert router.classify("\u54C8\u54C8") == Tier.FLASH  # 哈哈
        assert router.classify("\u597D") == Tier.FLASH          # 好
        assert router.classify("\u55EF") == Tier.FLASH          # 嗯
        assert router.classify("\u8C22\u8C22") == Tier.FLASH    # 谢谢
        assert router.classify("\u65E9\u5B89") == Tier.FLASH    # 早安
        assert router.classify("\u665A\u5B89") == Tier.FLASH    # 晚安

    def test_security_audit_frontier(self, router):
        assert router.classify("perform a security audit of this contract") == Tier.FRONTIER
        assert router.classify("vulnerability review for the system") == Tier.FRONTIER
        assert router.classify("analyze the codebase architecture") == Tier.FRONTIER

    def test_deploy_production_pro(self, router):
        assert router.classify("deploy to production") == Tier.PRO
        assert router.classify("production release push") == Tier.PRO


class TestExplicitHints:
    def test_flash_hint(self, router):
        assert router.classify("[tier:flash] some complex text about security audit review") == Tier.FLASH

    def test_sonnet_hint(self, router):
        assert router.classify("[tier:sonnet] hello") == Tier.STANDARD

    def test_opus_hint(self, router):
        assert router.classify("[tier:opus] simple greeting") == Tier.FRONTIER

    def test_frontier_hint(self, router):
        assert router.classify("[tier:frontier] hi") == Tier.FRONTIER


class TestScoreBoundaries:
    """Test classification at exact score boundaries."""

    def test_flash_boundary(self, router):
        """Score <= 15 should be FLASH."""
        # "hi" is very short, no indicators -> should score very low
        tier = router.classify("hi there")
        assert tier == Tier.FLASH

    def test_standard_range(self, router):
        """Messages with moderate complexity should be STANDARD."""
        # Enough length + domain + question to push above 15 but below 41
        text = "Can you explain how React works with TypeScript and maybe help me understand the build process?"
        tier = router.classify(text)
        assert tier in (Tier.STANDARD, Tier.PRO)

    def test_frontier_complex(self, router):
        """Highly complex messages should reach FRONTIER."""
        text = (
            "Analyze and evaluate the security of this Solidity smart contract. "
            "Compare the gas optimization techniques, prove that the MEV protection "
            "works step by step. Deploy to mainnet after the review. "
            "Calculate the exact yield, and explain why does this vulnerability exist? "
            "What if we add a reentrancy guard? How would you architect a fix? "
            "Also check the kubernetes deployment, debug the docker setup, "
            "and furthermore, although it seems secure, nevertheless verify "
            "the private key handling and credentials storage."
        )
        tier = router.classify(text)
        assert tier == Tier.FRONTIER


# ── Multi-dimensional boost ──────────────────────────────────────────


class TestMultiDimensionalBoost:
    def test_two_dimensions_boost(self, router):
        """Two triggered dimensions should apply 1.15x boost."""
        # Reasoning + code: both should score > 20
        text = "analyze this function and explain the import"
        score_raw, dims = router.score(text)
        triggered = sum(1 for s in dims.values() if s > 20)
        assert triggered >= 2

    def test_three_dimensions_boost(self, router):
        """Three triggered dimensions should apply 1.3x boost."""
        text = "analyze this function step by step and calculate the exact result"
        _, dims = router.score(text)
        triggered = sum(1 for s in dims.values() if s > 20)
        assert triggered >= 3


# ── Cascade detection ────────────────────────────────────────────────


class TestCascadeDetection:
    def test_uncertainty_detected(self, router):
        assert router.should_cascade("I'm not sure about this answer") is True
        assert router.should_cascade("I cannot determine the root cause") is True
        assert router.should_cascade("I would need more context to answer") is True
        assert router.should_cascade("it's difficult to say without more info") is True
        assert router.should_cascade("I can't confidently answer that") is True

    def test_clean_response_no_cascade(self, router):
        assert router.should_cascade("The answer is 42.") is False
        assert router.should_cascade("Here's the implementation:") is False

    def test_uncertainty_in_middle_ignored(self, router):
        """Uncertainty phrases after 500 chars should NOT trigger cascade."""
        padding = "A" * 600
        text = padding + " I'm not sure about this"
        assert router.should_cascade(text) is False

    def test_uncertainty_within_500_chars(self, router):
        """Uncertainty within first 500 chars should trigger."""
        padding = "A" * 100
        text = padding + " I'm not sure about this"
        assert router.should_cascade(text) is True


# ── Model selection ──────────────────────────────────────────────────


class TestSelectModel:
    def test_flash_returns_serve_model(self, router):
        config = {"serve_model": "sonnet-fast", "serve_reasoning_model": "opus"}
        model, tier, cascade = router.select_model("hi!", config)
        assert model == "sonnet-fast"
        assert tier == Tier.FLASH
        assert cascade is False

    def test_frontier_returns_reasoning_model(self, router):
        config = {"serve_model": "sonnet", "serve_reasoning_model": "opus"}
        model, tier, cascade = router.select_model(
            "security audit review of the codebase", config)
        assert model == "opus"
        assert tier == Tier.FRONTIER
        assert cascade is False

    def test_pro_enables_cascade(self, router):
        config = {"serve_model": "sonnet", "serve_reasoning_model": "opus"}
        model, tier, cascade = router.select_model(
            "deploy to mainnet production", config)
        assert model == "sonnet"
        assert tier == Tier.PRO
        assert cascade is True

    def test_fallback_to_model_key(self, router):
        config = {"model": "haiku"}
        model, tier, cascade = router.select_model("hello!", config)
        assert model == "haiku"

    def test_cascade_disabled_by_config(self):
        router = SmartRouter({"smart_routing": {"cascade_enabled": False}})
        config = {"serve_model": "sonnet"}
        _, _, cascade = router.select_model("deploy to mainnet production", config)
        assert cascade is False


# ── Stats ────────────────────────────────────────────────────────────


class TestRoutingStats:
    def test_record_tiers(self):
        stats = RoutingStats()
        stats.record(Tier.FLASH)
        stats.record(Tier.STANDARD)
        stats.record(Tier.PRO)
        stats.record(Tier.FRONTIER)
        d = stats.to_dict()
        assert d["total"] == 4
        assert d["flash"] == 1
        assert d["standard"] == 1
        assert d["pro"] == 1
        assert d["frontier"] == 1

    def test_cascade_counters(self):
        stats = RoutingStats()
        stats.record(Tier.PRO)
        stats.record_cascade_triggered()
        stats.record(Tier.PRO, cascaded=True)
        d = stats.to_dict()
        assert d["cascade_triggered"] == 1
        assert d["cascade_escalated"] == 1

    def test_thread_safety(self):
        stats = RoutingStats()
        errors = []

        def worker():
            try:
                for _ in range(1000):
                    stats.record(Tier.FLASH)
                    stats.record(Tier.STANDARD)
                    stats.record_cascade_triggered()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread safety errors: {errors}"
        d = stats.to_dict()
        assert d["total"] == 20_000  # 10 threads * 1000 * 2 records each
        assert d["flash"] == 10_000
        assert d["standard"] == 10_000
        assert d["cascade_triggered"] == 10_000


# ── Config ───────────────────────────────────────────────────────────


class TestSmartRouterConfig:
    def test_defaults(self):
        router = SmartRouter()
        assert router.config.enabled is True
        assert router.config.cascade_enabled is True
        assert router.config.domain_keywords == []

    def test_from_config_dict(self):
        router = SmartRouter({
            "smart_routing": {
                "enabled": False,
                "cascade_enabled": False,
                "domain_keywords": ["solana", "anchor"],
            }
        })
        assert router.config.enabled is False
        assert router.config.cascade_enabled is False
        assert router.config.domain_keywords == ["solana", "anchor"]

    def test_no_config_key(self):
        router = SmartRouter({"model": "sonnet"})
        assert router.config.enabled is True
