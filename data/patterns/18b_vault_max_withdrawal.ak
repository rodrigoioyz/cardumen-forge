use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName}
use cardano/fuzz as cfuzz

/// Withdrawal must not exceed a per-tx cap
fn withdrawal_within_cap(
  tokens:  dict.Dict<AssetName, Int>,
  max_qty: Int,
) -> Bool {
  when dict.to_pairs(tokens) is {
    [Pair(_, qty)] -> qty < 0 && -qty <= max_qty
    _              -> False
  }
}

/// Deposit must be a positive single token
fn deposit_valid(tokens: dict.Dict<AssetName, Int>) -> Bool {
  when dict.to_pairs(tokens) is {
    [Pair(_, qty)] -> qty > 0
    _              -> False
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_withdrawal_at_cap_accepted(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000)),
) {
  let (name, cap) = vals
  let tokens = dict.empty |> dict.insert(name, -cap)
  withdrawal_within_cap(tokens, cap)
}

test prop_withdrawal_over_cap_rejected(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000)),
) {
  let (name, cap) = vals
  let tokens = dict.empty |> dict.insert(name, -(cap + 1))
  !withdrawal_within_cap(tokens, cap)
}

test prop_deposit_positive_accepted(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_at_least(1)),
) {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, qty)
  deposit_valid(tokens)
}

test prop_empty_tokens_rejected() {
  !deposit_valid(dict.empty) && !withdrawal_within_cap(dict.empty, 100)
}
