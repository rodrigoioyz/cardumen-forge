use aiken/collection/list
use aiken/crypto.{blake2b_256}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/transaction.{OutputReference, Transaction}

pub type WhitelistDatum {
  merkle_root: ByteArray,
  max_depth:   Int,
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

/// Proof length must not exceed max_depth
fn within_depth(proof: List<ByteArray>, max_depth: Int) -> Bool {
  list.length(proof) <= max_depth
}

validator merkle_depth_limit {
  spend(
    datum: Option<WhitelistDatum>,
    redeemer: WhitelistRedeemer,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    within_depth(redeemer.proof, d.max_depth) && verify_proof(
      d.merkle_root,
      redeemer.leaf,
      redeemer.proof,
    )
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_within_depth_empty(max via fuzz.int_between(0, 10)) {
  within_depth([], max)
}

test prop_within_depth_exact(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.int_between(1, 5)),
) {
  let (node, depth) = vals
  let proof = list.repeat(node, depth)
  within_depth(proof, depth)
}

test prop_within_depth_exceeds_fails(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.int_between(1, 5)),
) {
  let (node, depth) = vals
  let proof = list.repeat(node, depth + 1)
  !within_depth(proof, depth)
}

test prop_verify_empty_proof(leaf via fuzz.bytearray_between(1, 32)) {
  let root = blake2b_256(leaf)
  verify_proof(root, leaf, [])
}
