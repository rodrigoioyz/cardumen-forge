
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

// ── Negative / fail tests ────────────────────────────────────────────────────

// A proof of length (depth+1) always exceeds max_depth, so within_depth
// must return False for every fuzzer draw.
test prop_fail_proof_exceeds_max_depth(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.int_between(0, 5)),
) fail {
  let (node, depth) = vals
  let proof = list.repeat(node, depth + 1)
  expect within_depth(proof, depth)
}

// A proof of 10 nodes can never fit inside a max_depth of 0..4,
// so within_depth must always return False.
test prop_fail_large_proof_zero_depth(
  node via fuzz.bytearray_between(1, 32),
) fail {
  let proof = list.repeat(node, 10)
  expect within_depth(proof, 0)
}

// verify_proof with a root that is all-zeros can never equal blake2b_256(leaf)
// for a valid leaf, so verify_proof must always return False.
test prop_fail_wrong_root_empty_proof(
  leaf via fuzz.bytearray_between(1, 32),
) fail {
  let wrong_root = #"0000000000000000000000000000000000000000000000000000000000000000"
  expect verify_proof(wrong_root, leaf, [])
}

// verify_proof on a single-sibling proof with the wrong root always fails.
test prop_fail_wrong_root_single_sibling(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.bytearray_between(1, 32)),
) fail {
  let (leaf, sibling) = vals
  let wrong_root = #"0000000000000000000000000000000000000000000000000000000000000000"
  expect verify_proof(wrong_root, leaf, [sibling])
}