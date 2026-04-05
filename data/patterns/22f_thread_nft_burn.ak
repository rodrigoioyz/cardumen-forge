
/// Thread NFT burn: exactly one token with qty == -1 in the mint field
use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName, PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
fn is_valid_burn(
  mint: assets.Value,
  auth_policy: PolicyId,
  auth_name: AssetName,
) -> Bool {
  assets.quantity_of(mint, auth_policy, auth_name) == -1
}

/// No other tokens are minted or burned alongside the thread NFT
fn only_thread_burned(
  mint: assets.Value,
  auth_policy: PolicyId,
) -> Bool {
  let tokens = assets.tokens(mint, auth_policy)
  dict.size(tokens) == 1
}

/// Full burn validation: exactly one NFT burned, nothing else minted under same policy
fn burn_valid(
  mint: assets.Value,
  auth_policy: PolicyId,
  auth_name: AssetName,
) -> Bool {
  is_valid_burn(mint, auth_policy, auth_name) && only_thread_burned(mint, auth_policy)
}

// ── Validator ────────────────────────────────────────────────────────────────

pub type BurnRedeemer {
  thread_name: AssetName,
}

validator thread_nft_burn {
  mint(redeemer: BurnRedeemer, policy_id: PolicyId, self: Transaction) {
    let mint = self.mint
    let thread_name = redeemer.thread_name
    let qty_correct = is_valid_burn(mint, policy_id, thread_name)
    let no_extras = only_thread_burned(mint, policy_id)
    let full_check = burn_valid(mint, policy_id, thread_name)
    qty_correct && no_extras && full_check
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_valid_burn_accepted(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let mint = assets.from_asset(policy, name, -1)
  burn_valid(mint, policy, name)
}

test prop_positive_qty_not_a_burn(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let mint = assets.from_asset(policy, name, 1)
  !is_valid_burn(mint, policy, name)
}

test prop_absent_nft_not_a_burn(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  !is_valid_burn(assets.zero, policy, name)
}

test prop_only_thread_burned_with_single_token(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let mint = assets.from_asset(policy, name, -1)
  only_thread_burned(mint, policy)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Zero quantity is not a valid burn (quantity must be exactly -1)
test prop_zero_qty_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  let mint = assets.from_asset(policy, name, 0)
  expect is_valid_burn(mint, policy, name)
}

/// A positive mint quantity is not a valid burn
test prop_mint_qty_rejected(
  vals via fuzz.both(
    fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
    fuzz.int_at_least(1),
  ),
) fail {
  let ((policy, name), qty) = vals
  let mint = assets.from_asset(policy, name, qty)
  expect is_valid_burn(mint, policy, name)
}

/// Empty value (zero) is rejected by is_valid_burn
test prop_empty_value_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  expect is_valid_burn(assets.zero, policy, name)
}

/// Two tokens under the same policy means only_thread_burned returns False
test prop_two_tokens_not_only_thread(
  vals via fuzz.both(
    cfuzz.policy_id(),
    fuzz.both(cfuzz.asset_name(), cfuzz.asset_name()),
  ),
) fail {
  let (policy, (name1, name2)) = vals
  // merge two distinct burns under the same policy
  let mint =
    assets.merge(
      assets.from_asset(policy, name1, -1),
      assets.from_asset(policy, name2, -1),
    )
  // only_thread_burned requires dict.size == 1; two distinct names → size == 2
  // (if name1 == name2 the quantities cancel to -2, still wrong; either way False)
  expect only_thread_burned(mint, policy)
}