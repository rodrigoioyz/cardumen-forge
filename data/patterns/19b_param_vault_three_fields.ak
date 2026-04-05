use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz

/// Commitment over three parameters: owner, asset_policy, nonce
fn param_hash3(
  owner:        ByteArray,
  asset_policy: ByteArray,
  nonce:        ByteArray,
) -> ByteArray {
  blake2b_224(
    owner
      |> bytearray.concat(asset_policy)
      |> bytearray.concat(nonce),
  )
}

/// Verify all three fields match the stored commitment
fn params_match3(
  owner:        ByteArray,
  asset_policy: ByteArray,
  nonce:        ByteArray,
  expected:     ByteArray,
) -> Bool {
  param_hash3(owner, asset_policy, nonce) == expected
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_correct_params_match(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) {
  let (owner, policy) = vals
  let nonce = #"cafebabe"
  let expected = param_hash3(owner, policy, nonce)
  params_match3(owner, policy, nonce, expected)
}

test prop_wrong_owner_fails(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) {
  let (owner, policy) = vals
  let nonce = #"cafebabe"
  let expected = param_hash3(owner, policy, nonce)
  !params_match3(#"deadbeef", policy, nonce, expected)
}

test prop_wrong_policy_fails(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) {
  let (owner, policy) = vals
  let nonce = #"cafebabe"
  let expected = param_hash3(owner, policy, nonce)
  !params_match3(owner, #"00112233", nonce, expected)
}

test prop_wrong_nonce_fails(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) {
  let (owner, policy) = vals
  let nonce = #"cafebabe"
  let expected = param_hash3(owner, policy, nonce)
  !params_match3(owner, policy, #"00000000", expected)
}
