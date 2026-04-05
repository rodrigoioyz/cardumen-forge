use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz

/// Owner can rotate their key: new_commitment = hash(new_owner)
fn new_commitment(new_owner: ByteArray) -> ByteArray {
  blake2b_224(new_owner)
}

/// Rotation is valid if old owner authorises AND new commitment is correct
fn rotation_valid(
  old_owner:      ByteArray,
  old_commitment: ByteArray,
  new_owner:      ByteArray,
  new_commitment_: ByteArray,
) -> Bool {
  blake2b_224(old_owner) == old_commitment
    && blake2b_224(new_owner) == new_commitment_
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_rotation_valid_with_correct_keys(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) {
  let (old_owner, new_owner) = vals
  let old_com = blake2b_224(old_owner)
  let new_com = blake2b_224(new_owner)
  rotation_valid(old_owner, old_com, new_owner, new_com)
}

test prop_wrong_old_owner_fails(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) {
  let (old_owner, new_owner) = vals
  let old_com = blake2b_224(old_owner)
  let new_com = blake2b_224(new_owner)
  !rotation_valid(#"deadbeef", old_com, new_owner, new_com)
}

test prop_new_commitment_correct(
  owner via cfuzz.verification_key_hash(),
) {
  new_commitment(owner) == blake2b_224(owner)
}

test prop_different_owners_differ(
  owner via cfuzz.verification_key_hash(),
) {
  // owner vs its hash — almost certainly different lengths, different hashes
  let alt = bytearray.concat(owner, #"ff")
  new_commitment(owner) != new_commitment(alt)
}
