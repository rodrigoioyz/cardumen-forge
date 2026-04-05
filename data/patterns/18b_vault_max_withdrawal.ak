
/// Withdrawal must not exceed a per-tx cap
use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName, PolicyId, flatten, tokens}
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
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

// ── Validator ─────────────────────────────────────────────────────────────────

pub type VaultRedeemer {
  Withdraw { max_qty: Int }
  Deposit
}

validator vault_max_withdrawal(policy_id: PolicyId) {
  mint(redeemer: VaultRedeemer, _self_policy: PolicyId, self: Transaction) {
    let minted_tokens = self.mint |> tokens(policy_id)
    when redeemer is {
      Withdraw { max_qty } ->
        withdrawal_within_cap(minted_tokens, max_qty)
      Deposit ->
        deposit_valid(minted_tokens)
    }
  }

  else(_) {
    fail
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

// ── Negative (fail) property tests ───────────────────────────────────────────

/// A withdrawal amount that exceeds the cap must always be rejected.
/// We pick qty = cap + over where over >= 1, so -qty < -cap, violating the cap.
test prop_withdrawal_over_cap_fails(
  vals via fuzz.both(
    cfuzz.asset_name(),
    fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
  ),
) fail {
  let (name, (cap, over)) = vals
  let tkns = dict.empty |> dict.insert(name, -(cap + over))
  expect withdrawal_within_cap(tkns, cap)
}

/// A deposit with a zero quantity is never valid (qty must be strictly positive).
test prop_deposit_zero_qty_fails(
  name via cfuzz.asset_name(),
) fail {
  let tkns = dict.empty |> dict.insert(name, 0)
  expect deposit_valid(tkns)
}

/// A deposit with a negative quantity is never valid.
test prop_deposit_negative_qty_fails(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_between(-10000, -1)),
) fail {
  let (name, qty) = vals
  let tkns = dict.empty |> dict.insert(name, qty)
  expect deposit_valid(tkns)
}

/// withdrawal_within_cap on an empty dict must always be rejected.
test prop_withdrawal_empty_dict_fails(
  cap via fuzz.int_at_least(1),
) fail {
  expect withdrawal_within_cap(dict.empty, cap)
}