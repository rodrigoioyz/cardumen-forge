use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}

/// Datum holds the blake2b_224 hash of the owner's verification key hash.
/// The redeemer provides the raw VKH so the validator can re-hash and compare.
pub type VaultDatum {
  owner_hash:   ByteArray,
  asset_policy: ByteArray,
}

pub type VaultRedeemer {
  owner_vkh:    ByteArray,
  asset_policy: ByteArray,
}

/// Hash a pair of parameters together (order-sensitive)
fn param_hash(owner: ByteArray, asset_policy: ByteArray) -> ByteArray {
  blake2b_224(bytearray.concat(owner, asset_policy))
}

/// The redeemer parameters must hash to match the stored datum commitment
fn params_match(
  owner_vkh:    ByteArray,
  asset_policy: ByteArray,
  expected:     ByteArray,
) -> Bool {
  param_hash(owner_vkh, asset_policy) == expected
}

validator parameterized_vault {
  spend(
    datum: Option<VaultDatum>,
    redeemer: VaultRedeemer,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    params_match(redeemer.owner_vkh, redeemer.asset_policy, d.owner_hash)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_param_hash_length(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) {
  let (owner, policy) = vals
  bytearray.length(param_hash(owner, policy)) == 28
}

test prop_param_hash_roundtrip(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) {
  let (owner, policy) = vals
  let h = param_hash(owner, policy)
  params_match(owner, policy, h)
}

test prop_param_hash_wrong_owner_fails(
  vals via fuzz.both(
    fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
    cfuzz.policy_id(),
  ),
) {
  let (owners, policy) = vals
  let (owner, wrong_owner) = owners
  let h = param_hash(owner, policy)
  if owner == wrong_owner {
    True
  } else {
    !params_match(wrong_owner, policy, h)
  }
}

test prop_param_hash_wrong_policy_fails(
  vals via fuzz.both(
    cfuzz.verification_key_hash(),
    fuzz.both(cfuzz.policy_id(), cfuzz.policy_id()),
  ),
) {
  let (owner, policies) = vals
  let (policy, wrong_policy) = policies
  let h = param_hash(owner, policy)
  if policy == wrong_policy {
    True
  } else {
    !params_match(owner, wrong_policy, h)
  }
}
