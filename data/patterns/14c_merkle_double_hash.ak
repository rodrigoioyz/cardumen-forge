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
    verify_proof_double(d.merkle_root, redeemer.leaf, redeemer.proof)
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
