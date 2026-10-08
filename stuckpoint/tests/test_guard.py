import pytest

from stuckpoint.llm.guard import check_no_code

CODE = [
    "Here you go:\n```python\ndef coinChange(coins, amount):\n    pass\n```",
    "Use `dp = [float('inf')] * (amount + 1)` to start.",
    "def coin_change(coins, amount):\n    return -1",
    "for (int i = 1; i <= amount; i++) {\n}",
    "for coin in coins:",
    "dp[i] = min(dp[i], dp[i - coin] + 1)",
    "Set best = min(best, ways[x - c] + 1) for every coin.",
    "vector<int> dp(amount + 1, INT_MAX);",
    "const f = (a) => a + 1",
    "    line one\n    line two\n    line three\n    line four",
    "Just do this: total += coin",
    "print(answer)",
    "int amount = 11;",
]

SAFE = [
    "What is the fewest number of coins you need for an amount of zero? Could that help you "
    "answer amount one, and then two?",
    "This is a dynamic programming problem: the best answer for an amount builds on the best "
    "answers for smaller amounts.",
    "1. Think of every amount from zero up to the target. 2. For each amount, consider ending "
    "with each coin. 3. Keep the smallest count you can reach. 4. If the target is never "
    "reachable, the answer is minus one.",
    "Try the example by hand with coins 1, 2 and 5 and amount 11.",
]


@pytest.mark.parametrize("text", CODE)
def test_blocks_code(text):
    ok, reason = check_no_code(text)
    assert not ok, f"should block: {text!r}"
    assert reason


@pytest.mark.parametrize("text", SAFE)
def test_allows_plain_hints(text):
    ok, reason = check_no_code(text)
    assert ok, f"false positive ({reason}): {text!r}"
