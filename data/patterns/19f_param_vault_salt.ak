
/// Salted commitment: prevents rainbow-table attacks on predictable inputs
use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
fn salted_hash(owner: ByteArray, salt: ByteArray) -> ByteArray {
  blake2b_224(bytearray.concat(salt, owner))
}

/// Verify owner against a salted commitment
fn salted_match(
  owner: ByteArray,
  salt: ByteArray,
  expected: ByteArray,
) -> Bool {
  salted_hash(owner, salt) == expected
}

/// Different salts produce different commitments for the same owner
fn salt_randomises(owner: ByteArray, s1: ByteArray, s2: ByteArray) -> Bool {
  s1 == s2 || salted_hash(owner, s1) != salted_hash(owner, s2)
}

// ── Datum / Redeemer types ───────────────────────────────────────────────────

pub type VaultDatum {
  commitment: ByteArray,
}

pub type VaultRedeemer {
  owner: ByteArray,
  salt: ByteArray,
}

// ── Validator ────────────────────────────────────────────────────────────────

validator param_vault_salt {
  spend(
    datum: Option<VaultDatum>,
    redeemer: VaultRedeemer,
    _output_reference: Data,
    _self: Transaction,
  ) {
    when datum is {
      None -> False
      Some(d) ->
        salted_match(redeemer.owner, redeemer.salt, d.commitment)
    }
  }

  else(_) {
    fail
  }
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A wrong owner never matches a commitment built for a different owner,
/// when both owners are drawn from a 28-byte hash space and the salt is fixed.
test prop_wrong_owner_rejected(
  vals via fuzz.both(
    cfuzz.verification_key_hash(),
    cfuzz.verification_key_hash(),
  ),
) fail {
  let (real_owner, wrong_owner) = vals
  // Build the commitment for real_owner; then attempt to match with wrong_owner.
  // salted_match returns False whenever real_owner != wrong_owner,
  // which is guaranteed (with overwhelming probability) for independent 28-byte hashes.
  let expected = salted_hash(real_owner, #"deadbeef")
  expect salted_match(wrong_owner, #"deadbeef", expected)
}

/// An all-zeros expected hash never matches any real salted commitment
/// because blake2b_224 never produces the all-zeros digest.
test prop_zero_commitment_never_matches() fail {
  let expected = #"0000000000000000000000000000000000000000000000000000000000000000"
  expect salted_match(#"aabbcc", #"ddeeff", expected)
}

/// salt_randomises must return True when the two salts differ;
/// forcing s1 == s2 == #"" would make the short-circuit `s1 == s2` branch fire and
/// return True — so instead we pick two provably distinct salts and a fixed owner,
/// then assert the hashes ARE equal (which they cannot be), proving False.
test prop_same_salt_same_hash_collision_impossible() fail {
  // salted_hash(#"cafe", #"aa") != salted_hash(#"cafe", #"bb") in practice,
  // so claiming they ARE equal should always fail.
  let h1 = salted_hash(#"cafe", #"aa")
  let h2 = salted_hash(#"cafe", #"bb")
  expect h1 == h2
}

/// Using an empty expected bytearray never satisfies salted_match because
/// blake2b_224 always produces a 28-byte digest, never an empty one.
test prop_empty_expected_never_matches(
  vals via fuzz.both(cfuzz.verification_key_hash(), fuzz.bytearray_between(1, 16)),
) fail {
  let (owner, salt) = vals
  expect salted_match(owner, salt, #"")
}