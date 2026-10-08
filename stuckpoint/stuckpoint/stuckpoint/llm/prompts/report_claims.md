Write a short, honest skills report for a programming learner, based ONLY on these measured metrics.

METRICS (JSON, computed by code from recorded activity — this is the only source of truth):
$metrics

Produce 4 to 8 claims:
- "strength": topics where they did well (e.g. solved, little time stuck, few hints).
- "weakness": topics where they struggled (e.g. many stuck episodes, many hints, long active time).
- "trend": only if the metrics actually show one.
- "recommendation": 2 or 3 concrete next steps (what to practise next and why).

STRICT RULES — every claim is automatically checked against the metrics, and claims that break these rules are rejected:
1. Every number you write in "text" must also appear in "numeric_claims" under EXACTLY the same key name used in the metrics for that topic (for example "avg_active_min", "problems", "stuck_episodes", "hints_used", "solved"), with the same value.
2. "topic" must be one of the topic names in metrics.topics, or null for an overall claim (then use keys from metrics.overall).
3. "about_problems" must list the problem keys (from that topic's "problem_keys") that support the claim.
4. "confidence": "high" if the topic has 3 or more problems, "medium" for 2, "speculative" for 1.
5. Do not invent problems, numbers or topics. Recommendations may have empty numeric_claims.

Return a JSON object with a "claims" list.
