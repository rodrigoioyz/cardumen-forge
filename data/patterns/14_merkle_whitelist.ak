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

/// Hash a pair of nodes deterministically (always sort to be order-independent)
fn hash_pair(a: ByteArray, b: ByteArray) -> ByteArray {
  if bytearray.compare(a, b) == Less {
    blake2b_256(bytearray.concat(a, b))
  } else {
    blake2b_256(bytearray.concat(b, a))
  }
}

/// Verify a Merkle inclusion proof
fn verify_proof(
  root:  ByteArray,
  leaf:  ByteArray,
  proof: List<ByteArray>,
) -> Bool {
  let computed =
    list.foldl(proof, blake2b_256(leaf), fn(sibling, current) {
      hash_pair(current, sibling)
    })
  computed == root
}

validator merkle_whitelist {
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
    let leaf_not_empty = bytearray.length(leaf) > 0
    let root_not_empty = bytearray.length(root) > 0
    let proof_not_empty = list.length(proof) >= 0
    let proof_valid = verify_proof(root, leaf, proof)
    leaf_not_empty && root_not_empty && proof_not_empty && proof_valid
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_verify_proof_empty_proof(leaf via fuzz.bytearray_between(1, 32)) {
  // Proof of length 0: computed = hash(leaf), must equal root = hash(leaf)
  let root = blake2b_256(leaf)
  verify_proof(root, leaf, [])
}

test prop_verify_proof_single_sibling(
  vals via fuzz.both(
    fuzz.bytearray_between(1, 32),
    fuzz.bytearray_between(1, 32),
  ),
) {
  let (leaf, sibling) = vals
  let root = hash_pair(blake2b_256(leaf), blake2b_256(sibling))
  verify_proof(root, leaf, [blake2b_256(sibling)])
}

test prop_hash_pair_symmetric(
  vals via fuzz.both(
    fuzz.bytearray_between(1, 16),
    fuzz.bytearray_between(1, 16),
  ),
) {
  let (a, b) = vals
  hash_pair(a, b) == hash_pair(b, a)
}

test prop_verify_proof_wrong_leaf_fails(
  vals via fuzz.both(
    fuzz.bytearray_between(1, 16),
    fuzz.bytearray_between(1, 16),
  ),
) fail {
  let (leaf, wrong_leaf) = vals
  if leaf == wrong_leaf {
    error
  } else {
    let root = blake2b_256(leaf)
    verify_proof(root, wrong_leaf, [])
  }
}