
/// Hash a sorted list of signers into a single commitment
/// Sort by prepending each then folding (deterministic ordering assumed)
use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction, OutputReference}
use aiken/collection/list
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

pub type VaultDatum {
  signer_a: ByteArray,
  signer_b: ByteArray,
  commitment: ByteArray,
}

pub type VaultRedeemer {
  provided_a: ByteArray,
  provided_b: ByteArray,
}

validator param_vault_multisig {
  spend(
    datum: Option<VaultDatum>,
    redeemer: VaultRedeemer,
    _ref: OutputReference,
    self: Transaction,
  ) {
    expect Some(d) = datum
    let params_ok =
      multisig_params_valid(redeemer.provided_a, redeemer.provided_b, d.commitment)
    let ordering_ok = order_matters(redeemer.provided_a, redeemer.provided_b)
    let signed_by_a =
      list.any(self.extra_signatories, fn(s) { s == redeemer.provided_a })
    let signed_by_b =
      list.any(self.extra_signatories, fn(s) { s == redeemer.provided_b })
    let signers_match_datum =
      redeemer.provided_a == d.signer_a && redeemer.provided_b == d.signer_b
    params_ok && ordering_ok && signed_by_a && signed_by_b && signers_match_datum
  }

  else(_) {
    fail
  }
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

// ── Negative (fail) tests ─────────────────────────────────────────────────────

/// A completely wrong commitment (all zeros) never matches the real hash
/// of any two distinct verification key hashes.
test prop_wrong_commitment_rejected(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) fail {
  let (s1, s2) = vals
  // #"00...00" (28 zero bytes) is an invalid commitment for any real hash pair
  expect multisig_params_valid(s1, s2, #"0000000000000000000000000000000000000000000000000000000000000000")
}

/// Swapping signer_a and signer_b always produces a different hash
/// when s1 != s2, so multisig_params_valid with swapped args must be False.
/// We force s1 != s2 by appending a distinct suffix byte to guarantee inequality.
test prop_swapped_args_always_rejected(
  s1 via cfuzz.verification_key_hash(),
) fail {
  // s2 is s1 with an extra byte appended — guaranteed s1 != s2
  let s2 = bytearray.concat(s1, #"ff")
  let expected = signers_hash(s1, s2)
  // passing (s2, s1) instead of (s1, s2) must fail
  expect multisig_params_valid(s2, s1, expected)
}

/// An empty expected commitment never matches a real blake2b_224 digest.
test prop_empty_commitment_rejected(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) fail {
  let (s1, s2) = vals
  expect multisig_params_valid(s1, s2, #"")
}

/// Appending an extra byte to signer_b corrupts the hash; the original
/// commitment no longer matches.
test prop_corrupted_signer_b_rejected(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) fail {
  let (s1, s2) = vals
  let expected = signers_hash(s1, s2)
  let corrupted_b = bytearray.concat(s2, #"ab")
  expect multisig_params_valid(s1, corrupted_b, expected)
}