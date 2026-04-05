
/// Commitment over three parameters: owner, asset_policy, nonce
use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
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

// ── Validator ────────────────────────────────────────────────────────────────

/// Datum holds the committed hash of (owner, asset_policy, nonce)
pub type VaultDatum {
  commitment: ByteArray,
}

/// Redeemer supplies the three plaintext fields for verification
pub type VaultRedeemer {
  owner: ByteArray,
  asset_policy: ByteArray,
  nonce: ByteArray,
}

validator param_vault_three_fields {
  spend(
    datum: Option<VaultDatum>,
    redeemer: VaultRedeemer,
    _output_reference: Data,
    _self: Transaction,
  ) {
    when datum is {
      None -> False
      Some(d) ->
        params_match3(
          redeemer.owner,
          redeemer.asset_policy,
          redeemer.nonce,
          d.commitment,
        )
    }
  }

  else(_) {
    fail
  }
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Wrong owner supplied — params_match3 must always return False
test prop_fail_wrong_owner(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) fail {
  let (owner, policy) = vals
  let nonce = #"cafebabe"
  let expected = param_hash3(owner, policy, nonce)
  // #"deadbeef" is a fixed 4-byte value; owner is a 28-byte vk hash,
  // so they can never be equal and the hash will differ.
  expect params_match3(#"deadbeef", policy, nonce, expected)
}

/// Wrong nonce supplied — params_match3 must always return False
test prop_fail_wrong_nonce(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) fail {
  let (owner, policy) = vals
  let nonce = #"cafebabe"
  let expected = param_hash3(owner, policy, nonce)
  // #"00000000" differs from #"cafebabe", so the hash never matches.
  expect params_match3(owner, policy, #"00000000", expected)
}

/// Wrong policy supplied — params_match3 must always return False
test prop_fail_wrong_policy(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) fail {
  let (owner, policy) = vals
  let nonce = #"cafebabe"
  let expected = param_hash3(owner, policy, nonce)
  // #"00112233" is a fixed 4-byte value; policy is 28 bytes, never equal.
  expect params_match3(owner, #"00112233", nonce, expected)
}

/// Completely zeroed-out commitment never matches a real hash
test prop_fail_zero_commitment(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.policy_id()),
) fail {
  let (owner, policy) = vals
  let nonce = #"cafebabe"
  // A 28-byte all-zero expected value is astronomically unlikely to equal
  // the real blake2b_224 hash — treat it as always-false.
  expect params_match3(owner, policy, nonce, #"0000000000000000000000000000000000000000000000000000000000")
}