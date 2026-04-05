
/// Hash includes a version byte to allow protocol upgrades
use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
fn versioned_hash(
  owner:   ByteArray,
  version: ByteArray,
) -> ByteArray {
  blake2b_224(bytearray.concat(version, owner))
}

/// Params match only when version also matches
fn versioned_match(
  owner:    ByteArray,
  version:  ByteArray,
  expected: ByteArray,
) -> Bool {
  versioned_hash(owner, version) == expected
}

/// Upgrading the version produces a different commitment
fn version_sensitive(
  owner: ByteArray,
  v1:    ByteArray,
  v2:    ByteArray,
) -> Bool {
  v1 == v2 || versioned_hash(owner, v1) != versioned_hash(owner, v2)
}

// ── Validator ────────────────────────────────────────────────────────────────

pub type VaultDatum {
  commitment: ByteArray,
  version: ByteArray,
}

pub type VaultRedeemer {
  owner: ByteArray,
  version: ByteArray,
}

validator param_vault_version {
  spend(
    datum: Option<VaultDatum>,
    redeemer: VaultRedeemer,
    _output_reference: Data,
    _self: Transaction,
  ) {
    when datum is {
      None -> False
      Some(d) -> {
        let VaultRedeemer { owner, version } = redeemer
        let matches = versioned_match(owner, version, d.commitment)
        let sensitive = version_sensitive(owner, d.version, version)
        matches && sensitive
      }
    }
  }

  else(_) {
    False
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_correct_version_matches(
  vals via fuzz.both(cfuzz.verification_key_hash(), fuzz.bytearray_between(1, 4)),
) {
  let (owner, version) = vals
  let expected = versioned_hash(owner, version)
  versioned_match(owner, version, expected)
}

test prop_wrong_version_fails(
  owner via cfuzz.verification_key_hash(),
) {
  let expected = versioned_hash(owner, #"01")
  !versioned_match(owner, #"02", expected)
}

test prop_version_sensitivity(
  owner via cfuzz.verification_key_hash(),
) {
  version_sensitive(owner, #"01", #"02")
}

test prop_same_version_matches(
  vals via fuzz.both(cfuzz.verification_key_hash(), fuzz.bytearray_between(1, 4)),
) {
  let (owner, version) = vals
  version_sensitive(owner, version, version)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// versioned_match must reject when the committed hash was built with a
/// different version byte (#"01") but we present #"02".
test prop_wrong_version_rejected(
  owner via cfuzz.verification_key_hash(),
) fail {
  let expected = versioned_hash(owner, #"01")
  expect versioned_match(owner, #"02", expected)
}

/// versioned_match must reject when the expected hash is the empty bytearray,
/// which can never equal a real blake2b_224 digest.
test prop_empty_expected_rejected(
  vals via fuzz.both(cfuzz.verification_key_hash(), fuzz.bytearray_between(1, 4)),
) fail {
  let (owner, version) = vals
  expect versioned_match(owner, version, #"")
}

/// versioned_match must reject when owner differs from the one used to build
/// the commitment, even if the version byte is correct.
test prop_wrong_owner_rejected(
  vals via fuzz.both(
    fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
    fuzz.bytearray_between(1, 4),
  ),
) fail {
  let ((owner_a, owner_b), version) = vals
  // Build commitment for owner_a, then try to open with owner_b.
  // When owner_a == owner_b the hashes are equal, so we need them distinct.
  // blake2b_224 is collision-resistant so distinct inputs always differ.
  let expected = versioned_hash(owner_a, version)
  // Guard: only meaningful when the two owners differ.
  // If they happen to be equal the helper returns True, but the fuzzer
  // almost never generates equal 28-byte arrays, so the test is sound.
  expect versioned_match(owner_b, version, expected)
}

/// version_sensitive must return False only when v1 == v2 AND the hashes
/// collide — which never happens for a cryptographic hash.  However,
/// the function returns False only when v1 != v2 AND hashes are equal,
/// which is a hash collision and therefore practically impossible.
/// A simpler guaranteed-false case: feed the same *non-equal* version bytes
/// whose hashes we force to be equal by using the empty owner, but since
/// blake2b_224 is collision-resistant we instead craft a case where
/// the function body reduces to False by exploiting the definition:
/// version_sensitive returns False iff v1 != v2 AND hash(v1)==hash(v2).
/// We cannot trigger that, so we target a known-bad usage of versioned_match:
/// matching against the wrong owner's commitment with the same version,
/// which is guaranteed to be False for any real owner pair.
test prop_swapped_owner_commitment_rejected() fail {
  let owner_a = #"aabbccdd"
  let owner_b = #"11223344"
  let version = #"ff"
  let expected = versioned_hash(owner_a, version)
  expect versioned_match(owner_b, version, expected)
}