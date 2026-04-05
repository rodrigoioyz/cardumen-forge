use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName, PolicyId}
use cardano/fuzz as cfuzz

/// Thread NFT burn: exactly one token with qty == -1 in the mint field
fn is_valid_burn(
  mint:        assets.Value,
  auth_policy: PolicyId,
  auth_name:   AssetName,
) -> Bool {
  assets.quantity_of(mint, auth_policy, auth_name) == -1
}

/// No other tokens are minted or burned alongside the thread NFT
fn only_thread_burned(
  mint:        assets.Value,
  auth_policy: PolicyId,
) -> Bool {
  let tokens = assets.tokens(mint, auth_policy)
  dict.size(tokens) == 1
}

/// Full burn validation: exactly one NFT burned, nothing else minted under same policy
fn burn_valid(
  mint:        assets.Value,
  auth_policy: PolicyId,
  auth_name:   AssetName,
) -> Bool {
  is_valid_burn(mint, auth_policy, auth_name) && only_thread_burned(mint, auth_policy)
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
