use aiken/collection/list
use aiken/crypto.{blake2b_224}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
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

pub type VaultDatum {
  owner: ByteArray,
  commitment: ByteArray,
}

pub type VaultRedeemer {
  new_owner: ByteArray,
}

validator param_vault {
  spend(datum: Option<VaultDatum>, redeemer: VaultRedeemer, _ref, self: Transaction) {
    expect Some(d) = datum
    let old_owner = d.owner
    let old_commitment = d.commitment
    let new_own = redeemer.new_owner
    let new_com = new_commitment(new_own)
    let signed = list.any(self.extra_signatories, fn(sig) { sig == old_owner })
    let valid = rotation_valid(old_owner, old_commitment, new_own, new_com)
    signed && valid
  }

  else(_) {
    fail
  }
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

// ── Negative / fail tests ─────────────────────────────────────────────────────

/// rotation_valid must fail when the old_commitment does not match blake2b_224(old_owner).
/// We supply a zeroed-out commitment that will never equal a real hash.
test prop_bad_old_commitment_rejected(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) fail {
  let (old_owner, new_owner) = vals
  let new_com = blake2b_224(new_owner)
  // #"0000000000000000000000000000000000000000000000000000000000000000"
  // is 32 zero bytes — blake2b_224 produces 28 bytes, so this never matches
  expect rotation_valid(old_owner, #"00000000000000000000000000000000000000000000000000000000", new_owner, new_com)
}

/// rotation_valid must fail when the new_commitment_ does not match blake2b_224(new_owner).
/// We supply a zeroed-out new commitment, guaranteeing a mismatch.
test prop_bad_new_commitment_rejected(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) fail {
  let (old_owner, new_owner) = vals
  let old_com = blake2b_224(old_owner)
  expect rotation_valid(old_owner, old_com, new_owner, #"00000000000000000000000000000000000000000000000000000000")
}

/// rotation_valid must fail when both commitments are wrong (all zeros).
test prop_both_commitments_wrong_rejected(
  vals via fuzz.both(cfuzz.verification_key_hash(), cfuzz.verification_key_hash()),
) fail {
  let (old_owner, new_owner) = vals
  expect rotation_valid(
    old_owner,
    #"00000000000000000000000000000000000000000000000000000000",
    new_owner,
    #"00000000000000000000000000000000000000000000000000000000",
  )
}

/// rotation_valid must fail when old_owner is the empty bytearray,
/// because blake2b_224(#"") will not equal a commitment derived from a real key.
test prop_empty_old_owner_wrong_commitment_rejected(
  new_owner via cfuzz.verification_key_hash(),
) fail {
  // Use a commitment built from a real key as the old_commitment so it can
  // never match blake2b_224(#"") unless the key itself hashes to that — impossible
  // for a randomly generated verification_key_hash.
  let old_com = blake2b_224(new_owner)
  let new_com = blake2b_224(new_owner)
  expect rotation_valid(#"", old_com, new_owner, new_com)
}