use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output}

/// Thread NFT must end up at an output controlled by the expected owner VKH
fn nft_at_owner(
  outputs:     List<Output>,
  auth_policy: PolicyId,
  auth_name:   ByteArray,
  owner_vkh:   ByteArray,
) -> Bool {
  let owner_addr = address.from_verification_key(owner_vkh)
  list.any(
    outputs,
    fn(o) {
      o.address == owner_addr
        && assets.quantity_of(o.value, auth_policy, auth_name) == 1
    },
  )
}

/// NFT must not be split across multiple outputs (quantity == 1 exactly once)
fn nft_unique(
  outputs:     List<Output>,
  auth_policy: PolicyId,
  auth_name:   ByteArray,
) -> Bool {
  let total = list.foldl(
    outputs,
    0,
    fn(o, acc) { acc + assets.quantity_of(o.value, auth_policy, auth_name) },
  )
  total == 1
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_nft_at_correct_owner(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.verification_key_hash()),
) {
  let (policy, owner) = vals
  let val = assets.from_asset(policy, #"aa", 1)
  let out = Output { address: address.from_verification_key(owner), value: val, datum: NoDatum, reference_script: None }
  nft_at_owner([out], policy, #"aa", owner)
}

test prop_nft_at_wrong_owner_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.verification_key_hash()),
) {
  let (policy, owner) = vals
  let val = assets.from_asset(policy, #"aa", 1)
  let out = Output { address: address.from_verification_key(#"deadbeef"), value: val, datum: NoDatum, reference_script: None }
  !nft_at_owner([out], policy, #"aa", owner)
}

test prop_nft_unique_single_output(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let val = assets.from_asset(policy, name, 1)
  let out = Output { address: address.from_verification_key(#"aabb"), value: val, datum: NoDatum, reference_script: None }
  nft_unique([out], policy, name)
}

test prop_nft_not_unique_when_absent(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  !nft_unique([], policy, name)
}
