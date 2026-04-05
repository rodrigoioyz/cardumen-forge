use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{AssetName, PolicyId, tokens}
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
fn name_allowed(name: AssetName, allowlist: List<AssetName>) -> Bool {
  list.has(allowlist, name)
}

/// Mint tokens must be a single name from the allowlist
fn allowlisted_mint(
  tokens_dict: dict.Dict<AssetName, Int>,
  allowlist: List<AssetName>,
) -> Bool {
  when dict.to_pairs(tokens_dict) is {
    [Pair(name, qty)] -> qty > 0 && name_allowed(name, allowlist)
    _                 -> False
  }
}

// ── Validator ────────────────────────────────────────────────────────────────

pub type VaultRedeemer {
  allowlist: List<AssetName>,
}

validator vault_allowlist(policy_id: PolicyId) {
  mint(redeemer: VaultRedeemer, _policy: PolicyId, self: Transaction) {
    let minted_tokens = tokens(self.mint, policy_id)
    let allowlist = redeemer.allowlist
    let allowlist_nonempty = !list.is_empty(allowlist)
    let mint_valid = allowlisted_mint(minted_tokens, allowlist)
    let minted_pairs = dict.to_pairs(minted_tokens)
    let all_names_allowed =
      list.all(minted_pairs, fn(p) {
        let Pair(name, _qty) = p
        name_allowed(name, allowlist)
      })
    allowlist_nonempty && mint_valid && all_names_allowed
  }

  else(_) {
    fail
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
  let tks = dict.empty |> dict.insert(name, 5)
  allowlisted_mint(tks, [name])
}

test prop_unlisted_deposit_rejected(
  name via cfuzz.asset_name(),
) {
  let tks = dict.empty |> dict.insert(name, 5)
  !allowlisted_mint(tks, [])
}

// ── Fail tests ───────────────────────────────────────────────────────────────

/// name_allowed always returns False when the allowlist is empty
test prop_name_not_in_empty_allowlist(
  name via cfuzz.asset_name(),
) fail {
  expect name_allowed(name, [])
}

/// allowlisted_mint returns False when the token dict is empty (no pairs)
test prop_empty_mint_dict_rejected(
  name via cfuzz.asset_name(),
) fail {
  expect allowlisted_mint(dict.empty, [name])
}

/// allowlisted_mint returns False when qty is zero (not > 0)
test prop_zero_qty_mint_rejected(
  name via cfuzz.asset_name(),
) fail {
  let tks = dict.empty |> dict.insert(name, 0)
  expect allowlisted_mint(tks, [name])
}

/// allowlisted_mint returns False when qty is negative
test prop_negative_qty_mint_rejected(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_between(-1000, -1)),
) fail {
  let (name, qty) = vals
  let tks = dict.empty |> dict.insert(name, qty)
  expect allowlisted_mint(tks, [name])
}