use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz

/// Salted commitment: prevents rainbow-table attacks on predictable inputs
fn salted_hash(owner: ByteArray, salt: ByteArray) -> ByteArray {
  blake2b_224(bytearray.concat(salt, owner))
}

/// Verify owner against a salted commitment
fn salted_match(
  owner:    ByteArray,
  salt:     ByteArray,
  expected: ByteArray,
) -> Bool {
  salted_hash(owner, salt) == expected
}

/// Different salts produce different commitments for the same owner
fn salt_randomises(owner: ByteArray, s1: ByteArray, s2: ByteArray) -> Bool {
  s1 == s2 || salted_hash(owner, s1) != salted_hash(owner, s2)
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_correct_salt_matches(
  vals via fuzz.both(cfuzz.verification_key_hash(), fuzz.bytearray_between(8, 16)),
) {
  let (owner, salt) = vals
  let expected = salted_hash(owner, salt)
  salted_match(owner, salt, expected)
}

test prop_wrong_salt_fails(
  vals via fuzz.both(cfuzz.verification_key_hash(), fuzz.bytearray_between(8, 16)),
) {
  let (owner, salt) = vals
  let expected = salted_hash(owner, salt)
  !salted_match(owner, #"00", expected)
}

test prop_salt_randomises_commitment(
  owner via cfuzz.verification_key_hash(),
) {
  salt_randomises(owner, #"aabbccdd", #"11223344")
}

test prop_unsalted_differs_from_salted(
  vals via fuzz.both(cfuzz.verification_key_hash(), fuzz.bytearray_between(1, 8)),
) {
  let (owner, salt) = vals
  // salted hash is different from hash(owner) alone (except vanishingly rarely)
  let plain = blake2b_224(owner)
  let salted = salted_hash(owner, salt)
  bytearray.length(salt) == 0 || plain != salted
}
