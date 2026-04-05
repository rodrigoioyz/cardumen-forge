use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName, PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
fn single_token_only(tokens: dict.Dict<AssetName, Int>) -> Bool {
  dict.size(tokens) == 1
}

/// The single token must have a non-zero quantity
fn non_zero_qty(tokens: dict.Dict<AssetName, Int>) -> Bool {
  when dict.to_pairs(tokens) is {
    [Pair(_, qty)] -> qty != 0
    _              -> False
  }
}

/// Both guards must pass
fn valid_vault_mint(tokens: dict.Dict<AssetName, Int>) -> Bool {
  single_token_only(tokens) && non_zero_qty(tokens)
}

// ── Validator ────────────────────────────────────────────────────────────────

validator vault_multi_token_guard {
  mint(_redeemer: Data, policy_id: PolicyId, self: Transaction) {
    let minted_tokens = assets.tokens(self.mint, policy_id)
    let only_one = single_token_only(minted_tokens)
    let qty_ok = non_zero_qty(minted_tokens)
    let combined = valid_vault_mint(minted_tokens)
    only_one && qty_ok && combined
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_single_nonzero_valid(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_at_least(1)),
) {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, qty)
  valid_vault_mint(tokens)
}

test prop_zero_qty_rejected(
  name via cfuzz.asset_name(),
) {
  let tokens = dict.empty |> dict.insert(name, 0)
  !valid_vault_mint(tokens)
}

test prop_empty_rejected() {
  !valid_vault_mint(dict.empty)
}

test prop_two_tokens_rejected() {
  // Two distinct hardcoded names — dict will contain both entries
  let tokens = dict.empty |> dict.insert(#"aa", 1) |> dict.insert(#"bb", 1)
  !single_token_only(tokens)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// empty dict has size 0, not 1 — single_token_only always returns False
test prop_fail_single_token_empty_dict() fail {
  expect single_token_only(dict.empty)
}

/// A dict with two distinct token names has size 2 — single_token_only always False
test prop_fail_single_token_two_entries() fail {
  let tokens =
    dict.empty |> dict.insert(#"aa", 1) |> dict.insert(#"bb", 2)
  expect single_token_only(tokens)
}

/// non_zero_qty on an empty dict hits the wildcard branch → always False
test prop_fail_non_zero_qty_empty_dict() fail {
  expect non_zero_qty(dict.empty)
}

/// valid_vault_mint with a zero quantity single token is always False
test prop_fail_valid_vault_mint_zero_qty(
  name via cfuzz.asset_name(),
) fail {
  let tokens = dict.empty |> dict.insert(name, 0)
  expect valid_vault_mint(tokens)
}