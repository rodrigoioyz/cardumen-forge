use aiken/collection/list
use aiken/crypto.{blake2b_256}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/transaction.{OutputReference, Transaction}

pub type WhitelistDatum {
  merkle_root: ByteArray,
}

pub type TwoLeafRedeemer {
  leaf_a:   ByteArray,
  proof_a:  List<ByteArray>,
  leaf_b:   ByteArray,
  proof_b:  List<ByteArray>,
}

fn hash_pair(a: ByteArray, b: ByteArray) -> ByteArray {
  if bytearray.compare(a, b) == Less {
    blake2b_256(bytearray.concat(a, b))
  } else {
    blake2b_256(bytearray.concat(b, a))
  }
}

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

validator merkle_two_leaves {
  spend(
    datum: Option<WhitelistDatum>,
    redeemer: TwoLeafRedeemer,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    verify_proof(d.merkle_root, redeemer.leaf_a, redeemer.proof_a) && verify_proof(
      d.merkle_root,
      redeemer.leaf_b,
      redeemer.proof_b,
    )
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_two_leaves_empty_proofs(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.bytearray_between(1, 32)),
) {
  let (leaf_a, leaf_b) = vals
  let root_a = blake2b_256(leaf_a)
  let root_b = blake2b_256(leaf_b)
  verify_proof(root_a, leaf_a, []) && verify_proof(root_b, leaf_b, [])
}

test prop_two_leaves_same_leaf(leaf via fuzz.bytearray_between(1, 32)) {
  let root = blake2b_256(leaf)
  verify_proof(root, leaf, []) && verify_proof(root, leaf, [])
}

test prop_hash_pair_symmetric(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.bytearray_between(1, 16)),
) {
  let (a, b) = vals
  hash_pair(a, b) == hash_pair(b, a)
}

test prop_verify_wrong_root_fails(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.bytearray_between(1, 32)),
) fail {
  let (leaf, wrong_leaf) = vals
  if leaf == wrong_leaf {
    error
  } else {
    let root = blake2b_256(leaf)
    verify_proof(root, wrong_leaf, [])
  }
}
