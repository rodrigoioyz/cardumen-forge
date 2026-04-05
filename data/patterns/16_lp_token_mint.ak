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
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    !dict.is_empty(tokens)
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
