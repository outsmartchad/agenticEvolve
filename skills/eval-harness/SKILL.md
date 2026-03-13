---
name: eval-harness
description: Formal evaluation framework implementing eval-driven development (EDD) — define pass/fail criteria before coding, measure agent reliability with pass@k metrics, create regression suites, and benchmark performance. Use when setting up EDD, defining success criteria before implementation, measuring reliability, benchmarking across model versions, or when the user says "how do we know this works", "define success criteria", "measure reliability", "benchmark this", or wants to verify agent quality systematically.
---

# Eval Harness

Eval-driven development: evals are the unit tests of AI development. Define what success looks like before you build, then measure whether you hit it.

## Why EDD Matters

Without evals, you're vibing. You might get lucky, but you can't tell if changes improved things or made them worse. EDD gives you a signal — pass@k across runs — that tells you whether your prompt, skill, or agent actually works reliably.

## Eval Types

### Capability Evals
Test if Claude can do something:
```
[CAPABILITY EVAL: feature-name]
Task: Description of what to accomplish
Success Criteria:
  - [ ] Criterion 1 (specific, verifiable)
  - [ ] Criterion 2
Expected Output: What good looks like
```

### Regression Evals
Ensure changes don't break existing functionality:
```
[REGRESSION EVAL: feature-name]
Baseline: SHA or checkpoint
Tests: existing-test-1: PASS/FAIL
Result: X/Y passed
```

## Grader Types

1. **Code-Based** — deterministic checks (grep, test suite, build). Preferred when possible.
2. **Model-Based** — Claude evaluates open-ended outputs (score 1-5). Use for subjective quality.
3. **Human** — flagged for manual review. Use for security-critical paths.

## Metrics

- **pass@k**: at least one success in k attempts. Target: pass@3 > 90%.
- **pass^k**: all k trials succeed. Use for critical paths where any failure is unacceptable.

## Workflow

### 1. Define (before coding)
```markdown
Capability Evals:
1. Can create new user account
2. Can validate email format
Regression Evals:
1. Existing login still works
Success Metrics:
- pass@3 > 90% for capability
- pass^3 = 100% for regression
```

### 2. Implement
Write code to pass the defined evals.

### 3. Evaluate
Run each eval, record PASS/FAIL per run.

### 4. Report
```
EVAL REPORT: feature-xyz
Capability: 3/3 passed
Regression: 3/3 passed
pass@1: 67% | pass@3: 100%
Status: READY FOR REVIEW
```

## Storage

```
.claude/evals/
  feature-xyz.md      # Definition
  feature-xyz.log     # Run history
  baseline.json       # Regression baselines
```

## Best Practices

1. Define evals BEFORE coding — this is the whole point
2. Run evals frequently — after every significant change
3. Track pass@k over time — are you getting more reliable or less?
4. Use code graders when possible — they're faster and more consistent
5. Human review for security — never fully automate security decisions
6. Keep evals fast — slow evals don't get run
7. Version evals with code — they're part of the specification

## Integration with agenticEvolve

Apply EDD to our own system:
- `/evolve` output: does the generated skill actually trigger? (pass@3 on trigger evals)
- `/absorb` output: does the created skill work? (capability eval on the absorbed pattern)
- Skill quality: use the skill-creator's eval framework to measure skill performance

Source: Adapted from [everything-claude-code](https://github.com/affaan-m/everything-claude-code) eval-harness skill
