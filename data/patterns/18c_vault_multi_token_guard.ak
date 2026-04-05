use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName}
use cardano/fuzz as cfuzz

/// Vault rejects mints that touch more than one token name
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
