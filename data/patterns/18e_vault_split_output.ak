
/// On withdrawal, the extracted qty plus remaining qty must equal original total
use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName, PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
fn split_valid(
  withdrawn_qty: Int,
  remaining_qty: Int,
  original_qty: Int,
) -> Bool {
  withdrawn_qty > 0 && remaining_qty >= 0 && withdrawn_qty + remaining_qty == original_qty
}

/// Token in mint dict has negative qty for withdrawal
fn withdrawal_qty(tokens: dict.Dict<AssetName, Int>) -> Option<Int> {
  when dict.to_pairs(tokens) is {
    [Pair(_, qty)] -> if qty < 0 { Some(-qty) } else { None }
    _              -> None
  }
}

pub type VaultRedeemer {
  remaining_qty: Int,
  original_qty: Int,
}

validator vault_split(policy_id: PolicyId) {
  mint(redeemer: VaultRedeemer, _policy: PolicyId, self: Transaction) {
    let minted_tokens =
      self.mint
        |> assets.tokens(policy_id)
    when withdrawal_qty(minted_tokens) is {
      Some(withdrawn) ->
        split_valid(withdrawn, redeemer.remaining_qty, redeemer.original_qty)
      None -> False
    }
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_split_sums_to_original(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(0, 500)),
) {
  let (withdrawn, remaining) = vals
  split_valid(withdrawn, remaining, withdrawn + remaining)
}

test prop_zero_withdrawal_rejected(
  remaining via fuzz.int_between(0, 1000),
) {
  !split_valid(0, remaining, remaining)
}

test prop_over_withdrawal_rejected(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(1, 500)),
) {
  let (withdrawn, original) = vals
  // withdrawn > original means remaining would be negative
  !split_valid(withdrawn + original + 1, 0, original)
}

test prop_withdrawal_qty_from_dict(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000)),
) {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, -qty)
  withdrawal_qty(tokens) == Some(qty)
}

// ── Negative / fail tests ─────────────────────────────────────────────────────

/// Zero withdrawal is never valid — split_valid returns False when withdrawn_qty == 0
test prop_fail_zero_withdrawal(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(0, 500)),
) fail {
  let (remaining, original) = vals
  expect split_valid(0, remaining, original)
}

/// Negative withdrawal is never valid — split_valid requires withdrawn_qty > 0
test prop_fail_negative_withdrawal(
  vals via fuzz.both(fuzz.int_between(-500, -1), fuzz.int_between(0, 500)),
) fail {
  let (withdrawn, remaining) = vals
  // original = withdrawn + remaining could be anything; withdrawn <= 0 always fails
  expect split_valid(withdrawn, remaining, withdrawn + remaining)
}

/// Negative remaining qty is never valid — split_valid requires remaining_qty >= 0
test prop_fail_negative_remaining(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(-500, -1)),
) fail {
  let (withdrawn, remaining) = vals
  expect split_valid(withdrawn, remaining, withdrawn + remaining)
}

/// A positive qty in the mint dict is not a withdrawal — withdrawal_qty returns None
test prop_fail_positive_qty_not_withdrawal(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000)),
) fail {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, qty)
  expect withdrawal_qty(tokens) == Some(qty)
}