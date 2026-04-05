use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz

/// Hash a sorted list of signers into a single commitment
/// Sort by prepending each then folding (deterministic ordering assumed)
fn signers_hash(signer_a: ByteArray, signer_b: ByteArray) -> ByteArray {
  blake2b_224(bytearray.concat(signer_a, signer_b))
}

/// Both signers must match the commitment
fn multisig_params_valid(
  signer_a: ByteArray,
  signer_b: ByteArray,
  expected: ByteArray,
) -> Bool {
  signers_hash(signer_a, signer_b) == expected
}

/// Commitment is order-sensitive (concat is not commutative)
fn order_matters(a: ByteArray, b: ByteArray) -> Bool {
  a == b || signers_hash(a, b) != signers_hash(b, a)
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_correct_signers_match(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) {
  let (s1, s2) = vals
  let expected = signers_hash(s1, s2)
  multisig_params_valid(s1, s2, expected)
}

test prop_swapped_signers_fail(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) {
  let (s1, s2) = vals
  let expected = signers_hash(s1, s2)
  // swapping signers should fail unless s1 == s2
  s1 == s2 || !multisig_params_valid(s2, s1, expected)
}

test prop_order_sensitivity(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) {
  let (s1, s2) = vals
  order_matters(s1, s2)
}

test prop_wrong_signer_fails(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) {
  let (s1, s2) = vals
  let expected = signers_hash(s1, s2)
  !multisig_params_valid(s1, bytearray.concat(s2, #"00"), expected)
}
