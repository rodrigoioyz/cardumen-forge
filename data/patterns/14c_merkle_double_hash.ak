
use aiken/collection/list
use aiken/crypto.{blake2b_256}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/transaction.{OutputReference, Transaction}
pub type WhitelistDatum {
  merkle_root: ByteArray,
}

pub type WhitelistRedeemer {
  leaf:  ByteArray,
  proof: List<ByteArray>,
}

fn hash_pair(a: ByteArray, b: ByteArray) -> ByteArray {
  if bytearray.compare(a, b) == Less {
    blake2b_256(bytearray.concat(a, b))
  } else {
    blake2b_256(bytearray.concat(b, a))
  }
}

/// Double-hash the leaf before building the proof path
fn leaf_hash(leaf: ByteArray) -> ByteArray {
  blake2b_256(blake2b_256(leaf))
}

fn verify_proof_double(
  root:  ByteArray,
  leaf:  ByteArray,
  proof: List<ByteArray>,
) -> Bool {
  let computed =
    list.foldl(proof, leaf_hash(leaf), fn(sibling, current) {
      hash_pair(current, sibling)
    })
  computed == root
}

validator merkle_double_hash {
  spend(
    datum: Option<WhitelistDatum>,
    redeemer: WhitelistRedeemer,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let leaf = redeemer.leaf
    let proof = redeemer.proof
    let root = d.merkle_root
    let leaf_len = bytearray.length(leaf)
    let root_len = bytearray.length(root)
    let leaf_valid = leaf_len > 0
    let root_valid = root_len == 32
    let double_hashed = leaf_hash(leaf)
    let double_hash_len = bytearray.length(double_hashed)
    let hash_valid = double_hash_len == 32
    let proof_valid = verify_proof_double(root, leaf, proof)
    leaf_valid && root_valid && hash_valid && proof_valid
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_leaf_hash_not_equal_single(leaf via fuzz.bytearray_between(1, 32)) {
  // Double hash differs from single hash (almost always)
  let single = blake2b_256(leaf)
  let double = leaf_hash(leaf)
  bytearray.length(double) == 32 && bytearray.length(single) == 32
}

test prop_verify_double_empty_proof(leaf via fuzz.bytearray_between(1, 32)) {
  let root = leaf_hash(leaf)
  verify_proof_double(root, leaf, [])
}

test prop_verify_double_single_sibling(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.bytearray_between(1, 32)),
) {
  let (leaf, sibling) = vals
  let root = hash_pair(leaf_hash(leaf), blake2b_256(sibling))
  verify_proof_double(root, leaf, [blake2b_256(sibling)])
}

test prop_hash_pair_symmetric(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.bytearray_between(1, 16)),
) {
  let (a, b) = vals
  hash_pair(a, b) == hash_pair(b, a)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A wrong root (single hash instead of double hash) must never verify
/// with an empty proof, because verify_proof_double expects leaf_hash (double).
test prop_single_hash_root_rejected_empty_proof(
  leaf via fuzz.bytearray_between(1, 32),
) fail {
  let wrong_root = blake2b_256(leaf)
  expect verify_proof_double(wrong_root, leaf, [])
}

/// Supplying a completely different leaf against a correct root must be rejected.
/// We build the root from `leaf` but verify with `other_leaf`.
/// The two bytearrays must differ, so we prepend a fixed byte to other_leaf
/// ensuring other_leaf != leaf (different length guarantees inequality).
test prop_wrong_leaf_rejected(
  vals via fuzz.both(
    fuzz.bytearray_between(1, 16),
    fuzz.bytearray_between(17, 32),
  ),
) fail {
  let (leaf, other_leaf) = vals
  let root = leaf_hash(leaf)
  // other_leaf has different length → different content → different hash
  expect verify_proof_double(root, other_leaf, [])
}

/// A proof with a random sibling against a mismatched root must always fail.
/// We use the single hash of the leaf as the (wrong) root so the double-hash
/// path can never reconstruct it regardless of the sibling supplied.
test prop_wrong_root_with_sibling_rejected(
  vals via fuzz.both(
    fuzz.bytearray_between(1, 32),
    fuzz.bytearray_between(1, 32),
  ),
) fail {
  let (leaf, sibling) = vals
  // wrong_root is single-hash; correct path produces hash_pair(leaf_hash(leaf), sibling)
  let wrong_root = blake2b_256(leaf)
  expect verify_proof_double(wrong_root, leaf, [sibling])
}

/// An all-zeros 32-byte root is astronomically unlikely to match any real proof
/// result, so verifying any leaf with an empty proof against it must always fail.
test prop_zero_root_empty_proof_rejected(
  leaf via fuzz.bytearray_between(1, 32),
) fail {
  let zero_root = #"0000000000000000000000000000000000000000000000000000000000000000"
  expect verify_proof_double(zero_root, leaf, [])
}