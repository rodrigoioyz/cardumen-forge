use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz

/// Hash includes a version byte to allow protocol upgrades
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
