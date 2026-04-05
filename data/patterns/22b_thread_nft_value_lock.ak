use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output}

/// The continuing output must carry at least min_lovelace in addition to the NFT
fn value_locked_ok(
  output:       Output,
  auth_policy:  PolicyId,
  auth_name:    ByteArray,
  min_lovelace: Int,
) -> Bool {
  assets.quantity_of(output.value, auth_policy, auth_name) == 1
    && assets.lovelace_of(output.value) >= min_lovelace
}

/// Find the first output that satisfies value_locked_ok
fn find_locked_output(
  outputs:      List<Output>,
  auth_policy:  PolicyId,
  auth_name:    ByteArray,
  min_lovelace: Int,
) -> Option<Output> {
  list.find(
    outputs,
    fn(o) { value_locked_ok(o, auth_policy, auth_name, min_lovelace) },
  )
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_output_with_nft_and_lovelace_found(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let nft_val = assets.from_asset(policy, name, 1)
  let val     = assets.merge(nft_val, assets.from_lovelace(2_000_000))
  let out     = Output { address: address.from_verification_key(#"aabb"), value: val, datum: NoDatum, reference_script: None }
  value_locked_ok(out, policy, name, 2_000_000)
}

test prop_output_missing_nft_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let val = assets.from_lovelace(5_000_000)
  let out = Output { address: address.from_verification_key(#"aabb"), value: val, datum: NoDatum, reference_script: None }
  !value_locked_ok(out, policy, name, 2_000_000)
}

test prop_output_insufficient_lovelace_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let nft_val = assets.from_asset(policy, name, 1)
  let val     = assets.merge(nft_val, assets.from_lovelace(1_000_000))
  let out     = Output { address: address.from_verification_key(#"aabb"), value: val, datum: NoDatum, reference_script: None }
  !value_locked_ok(out, policy, name, 2_000_000)
}

test prop_find_returns_none_on_empty() {
  find_locked_output([], #"aabb", #"ccdd", 1_000_000) == None
}
