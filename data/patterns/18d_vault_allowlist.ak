use aiken/collection/dict
use aiken/collection/list
use cardano/assets.{AssetName}
use cardano/fuzz as cfuzz

/// Only token names on the allowlist can be deposited
fn name_allowed(name: AssetName, allowlist: List<AssetName>) -> Bool {
  list.has(allowlist, name)
}

/// Mint tokens must be a single name from the allowlist
fn allowlisted_mint(
  tokens:    dict.Dict<AssetName, Int>,
  allowlist: List<AssetName>,
) -> Bool {
  when dict.to_pairs(tokens) is {
    [Pair(name, qty)] -> qty > 0 && name_allowed(name, allowlist)
    _                 -> False
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_allowed_name_accepted(
  name via cfuzz.asset_name(),
) {
  name_allowed(name, [name, #"dead", #"beef"])
}

test prop_unknown_name_rejected(
  name via cfuzz.asset_name(),
) {
  !name_allowed(name, [])
}

test prop_allowlisted_deposit_valid(
  name via cfuzz.asset_name(),
) {
  let tokens = dict.empty |> dict.insert(name, 5)
  allowlisted_mint(tokens, [name])
}

test prop_unlisted_deposit_rejected(
  name via cfuzz.asset_name(),
) {
  let tokens = dict.empty |> dict.insert(name, 5)
  !allowlisted_mint(tokens, [])
}
