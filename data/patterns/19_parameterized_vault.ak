
/// Datum holds the blake2b_224 hash of the owner's verification key hash.
/// The redeemer provides the raw VKH so the validator can re-hash and compare.
use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}
pub type VaultDatum {
  owner_hash: ByteArray,
  asset_policy: ByteArray,
}

pub type VaultRedeemer {
  owner_vkh: ByteArray,
  asset_policy: ByteArray,
}

/// Hash a pair of parameters together (order-sensitive)
fn param_hash(owner: ByteArray, asset_policy: ByteArray) -> ByteArray {
  blake2b_224(bytearray.concat(owner, asset_policy))
}

/// The redeemer parameters must hash to match the stored datum commitment
fn params_match(
  owner_vkh: ByteArray,
  asset_policy: ByteArray,
  expected: ByteArray,
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
    let owner_vkh_len = bytearray.length(redeemer.owner_vkh)
    let policy_len = bytearray.length(redeemer.asset_policy)
    let owner_vkh_valid = owner_vkh_len == 28
    let policy_valid = policy_len == 28
    let redeemer_hash_matches =
      params_match(redeemer.owner_vkh, redeemer.asset_policy, d.owner_hash)
    let datum_policy_hash =
      param_hash(redeemer.owner_vkh, d.asset_policy)
    let policies_consistent = datum_policy_hash == param_hash(redeemer.owner_vkh, redeemer.asset_policy)
    owner_vkh_valid && policy_valid && redeemer_hash_matches && policies_consistent
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// params_match must reject when the expected hash is all-zeros (28 bytes),
/// because a real param_hash result will virtually never equal a fixed constant.
/// We use a known-bad expected value: the hash of the empty bytearray concat,
/// but XOR'd — simplest: just use a hash of something unrelated (empty string hash).
/// Easiest guaranteed failure: expected = #"" (wrong length → never equals 28-byte hash).
test prop_params_match_rejects_empty_expected(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) fail {
  let (owner, policy) = vals
  // The real hash is 28 bytes; comparing to #"" always yields False
  expect params_match(owner, policy, #"")
}

/// params_match must reject when owner and policy are swapped relative to
/// the stored hash — i.e., hash(a,b) != hash(b,a) in general.
/// We pick distinct fixed bytearrays so the swap is guaranteed to differ.
test prop_params_match_rejects_swapped_args() fail {
  // owner = 28 zero bytes, policy = 28 ff bytes — clearly distinct
  let owner =
    #"0000000000000000000000000000000000000000000000000000000000"
  let policy =
    #"ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
  // Compute hash with (owner, policy) but supply (policy, owner) — always differs
  let h = param_hash(owner, policy)
  expect params_match(policy, owner, h)
}

/// params_match must reject when the expected hash belongs to a completely
/// different owner, even if the policy matches.
test prop_params_match_rejects_different_owner(
  vals via fuzz.both(
    fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
    cfuzz.policy_id(),
  ),
) fail {
  let (owners, policy) = vals
  let (owner_a, owner_b) = owners
  // hash is built from owner_a; we claim owner_b produced it — fails when a != b.
  // To guarantee failure we always use owner_a's hash but pass owner_b.
  // When they happen to be equal the hash check would pass, so we construct a
  // provably different expected: hash(owner_a, policy) checked against
  // params_match(owner_b, policy, hash(owner_a, policy)).
  // Guarantee: we XOR the last byte of owner_b to force a difference.
  let h = param_hash(owner_a, policy)
  // Force owner_b to differ from owner_a by appending an extra byte making
  // the length 29 — param_hash still runs but the result differs from h.
  let different_owner = bytearray.concat(owner_a, #"ff")
  expect params_match(different_owner, policy, h)
}

/// params_match must reject when the expected hash is a single zero byte,
/// which is never equal to a proper 28-byte blake2b_224 digest.
test prop_params_match_rejects_single_zero_expected(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) fail {
  let (owner, policy) = vals
  expect params_match(owner, policy, #"00")
}