
use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{AssetName, PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
pub type PoolDatum {
  reserve_a:  Int,
  reserve_b:  Int,
  total_lp:   Int,
  lp_policy:  PolicyId,
}

/// LP tokens minted proportionally to the smaller side of the deposit
/// lp_out = min(input_a * total_lp / reserve_a, input_b * total_lp / reserve_b)
fn proportional_lp(input: Int, reserve: Int, total_lp: Int) -> Int {
  input * total_lp / reserve
}

fn lp_for_deposit(
  input_a:   Int,
  input_b:   Int,
  reserve_a: Int,
  reserve_b: Int,
  total_lp:  Int,
) -> Int {
  let lp_a = proportional_lp(input_a, reserve_a, total_lp)
  let lp_b = proportional_lp(input_b, reserve_b, total_lp)
  if lp_a <= lp_b {
    lp_a
  } else {
    lp_b
  }
}

/// Tokens returned on withdrawal: lp_burned * reserve / total_lp
fn lp_for_withdrawal(lp_burned: Int, total_lp: Int, reserve: Int) -> Int {
  lp_burned * reserve / total_lp
}

/// Minted LP must match the expected deposit amount
fn mint_amount_valid(
  tokens:    dict.Dict<AssetName, Int>,
  expected:  Int,
) -> Bool {
  let total = list.foldl(dict.values(tokens), 0, fn(qty, acc) { acc + qty })
  total == expected
}

validator lp_token_mint {
  mint(
    redeemer: PoolDatum,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    let PoolDatum { reserve_a, reserve_b, total_lp, .. } = redeemer
    expect reserve_a > 0
    expect reserve_b > 0
    expect total_lp > 0
    expect !dict.is_empty(tokens)
    let input_a = reserve_a / 10
    let input_b = reserve_b / 10
    let expected_lp =
      lp_for_deposit(input_a, input_b, reserve_a, reserve_b, total_lp)
    expect expected_lp > 0
    let withdrawal_check = lp_for_withdrawal(expected_lp, total_lp, reserve_a)
    expect withdrawal_check >= 0
    mint_amount_valid(tokens, expected_lp)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_proportional_lp_exact(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (reserve, total_lp) = vals
  proportional_lp(reserve, reserve, total_lp) == total_lp
}

test prop_lp_deposit_takes_minimum(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (reserve, total_lp) = vals
  let lp = lp_for_deposit(reserve, reserve * 2, reserve, reserve, total_lp)
  lp == total_lp
}

test prop_lp_withdrawal_proportional(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (reserve, total_lp) = vals
  lp_for_withdrawal(total_lp, total_lp, reserve) == reserve
}

test prop_lp_withdrawal_partial(
  vals via fuzz.both(fuzz.int_at_least(2), fuzz.int_between(1, 1000)),
) {
  let (total_lp, reserve) = vals
  let half = total_lp / 2
  lp_for_withdrawal(half, total_lp, reserve) <= reserve
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// mint_amount_valid with an empty token dict never equals a positive expected
test prop_mint_amount_valid_empty_tokens_fails(
  expected via fuzz.int_at_least(1),
) fail {
  expect mint_amount_valid(dict.empty, expected)
}

/// mint_amount_valid rejects when the summed tokens exceed expected
/// We put total = expected + gap (gap >= 1) so total != expected always
test prop_mint_amount_valid_over_minted_fails(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 500)),
) fail {
  let (expected, gap) = vals
  // Build a single-entry dict whose value is expected + gap
  let tokens =
    dict.insert(dict.empty, "lp", expected + gap)
  expect mint_amount_valid(tokens, expected)
}

/// mint_amount_valid rejects when the summed tokens are less than expected
/// We put total = expected - gap (gap >= 1, expected >= gap+1) so total != expected
test prop_mint_amount_valid_under_minted_fails(
  vals via fuzz.both(fuzz.int_between(2, 1000), fuzz.int_between(1, 500)),
) fail {
  let (base, gap) = vals
  let expected = base + gap
  // dict value is base, which equals expected - gap < expected
  let tokens =
    dict.insert(dict.empty, "lp", base)
  expect mint_amount_valid(tokens, expected)
}

/// proportional_lp with input=0 always returns 0, which != total_lp when total_lp >= 1
test prop_proportional_lp_zero_input_fails(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) fail {
  let (reserve, total_lp) = vals
  // proportional_lp(0, reserve, total_lp) == 0, never == total_lp (>= 1)
  expect proportional_lp(0, reserve, total_lp) == total_lp
}