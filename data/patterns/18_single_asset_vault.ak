
use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName, PolicyId, lovelace_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}
pub type VaultDatum {
  owner:      ByteArray,
  asset_policy: PolicyId,
}

pub type VaultRedeemer {
  Deposit
  Withdraw
}

/// Extract the single (name, qty) pair from a policy's tokens.
/// Returns None if the value contains zero or more than one token name.
fn get_single_token(
  tokens: dict.Dict<AssetName, Int>,
) -> Option<(AssetName, Int)> {
  when dict.to_pairs(tokens) is {
    [Pair(name, qty)] -> Some((name, qty))
    _                 -> None
  }
}

/// Deposit is valid when the value carries exactly one token name from the
/// vault's policy and its quantity is positive
fn deposit_valid(
  tokens: dict.Dict<AssetName, Int>,
) -> Bool {
  when get_single_token(tokens) is {
    Some((_, qty)) -> qty > 0
    None           -> False
  }
}

/// Withdrawal: exactly one token name from the policy, negative quantity
fn withdrawal_valid(
  tokens: dict.Dict<AssetName, Int>,
) -> Bool {
  when get_single_token(tokens) is {
    Some((_, qty)) -> qty < 0
    None           -> False
  }
}

validator single_asset_vault {
  spend(
    datum: Option<VaultDatum>,
    redeemer: VaultRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let tokens = assets.tokens(self.mint, d.asset_policy)
    when redeemer is {
      Deposit  -> deposit_valid(tokens)
      Withdraw -> withdrawal_valid(tokens)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_get_single_token_one(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_at_least(1)),
) {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, qty)
  get_single_token(tokens) == Some((name, qty))
}

test prop_get_single_token_empty_none() {
  get_single_token(dict.empty) == None
}

test prop_deposit_valid_positive(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_at_least(1)),
) {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, qty)
  deposit_valid(tokens)
}

test prop_deposit_invalid_negative(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_at_least(1)),
) {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, -qty)
  !deposit_valid(tokens) && withdrawal_valid(tokens)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// deposit_valid must reject an empty token dict (no tokens present)
test prop_deposit_valid_empty_tokens_rejected() fail {
  expect deposit_valid(dict.empty)
}

/// deposit_valid must reject a token with a non-positive (zero or negative) quantity
test prop_deposit_valid_zero_qty_rejected(
  name via cfuzz.asset_name(),
) fail {
  let tokens = dict.empty |> dict.insert(name, 0)
  expect deposit_valid(tokens)
}

/// withdrawal_valid must reject an empty token dict (no tokens present)
test prop_withdrawal_valid_empty_tokens_rejected() fail {
  expect withdrawal_valid(dict.empty)
}

/// withdrawal_valid must reject a token with a positive quantity
test prop_withdrawal_valid_positive_qty_rejected(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_at_least(1)),
) fail {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, qty)
  expect withdrawal_valid(tokens)
}