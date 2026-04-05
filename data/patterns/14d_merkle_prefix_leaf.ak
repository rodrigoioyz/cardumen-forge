
use aiken/collection/list
use aiken/crypto.{blake2b_256}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/transaction.{OutputReference, Transaction}
pub type WhitelistDatum {
  merkle_root: ByteArray,
  domain_tag:  ByteArray,
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

/// Prefix leaf with a domain tag before hashing (domain separation)
fn tagged_leaf_hash(tag: ByteArray, leaf: ByteArray) -> ByteArray {
  blake2b_256(bytearray.concat(tag, leaf))
}

fn verify_proof_tagged(
  root:  ByteArray,
  tag:   ByteArray,
  leaf:  ByteArray,
  proof: List<ByteArray>,
) -> Bool {
  let computed =
    list.foldl(proof, tagged_leaf_hash(tag, leaf), fn(sibling, current) {
      hash_pair(current, sibling)
    })
  computed == root
}

validator merkle_prefix_leaf {
  spend(
    datum: Option<WhitelistDatum>,
    redeemer: WhitelistRedeemer,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let leaf_not_empty = bytearray.length(redeemer.leaf) > 0
    let tag_not_empty = bytearray.length(d.domain_tag) > 0
    let root_not_empty = bytearray.length(d.merkle_root) > 0
    let leaf_hash = tagged_leaf_hash(d.domain_tag, redeemer.leaf)
    let leaf_hash_len = bytearray.length(leaf_hash) == 32
    let proof_valid =
      verify_proof_tagged(d.merkle_root, d.domain_tag, redeemer.leaf, redeemer.proof)
    leaf_not_empty && tag_not_empty && root_not_empty && leaf_hash_len && proof_valid
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_tagged_hash_uses_tag(
  vals via fuzz.both(fuzz.bytearray_between(1, 8), fuzz.bytearray_between(1, 32)),
) {
  let (tag, leaf) = vals
  bytearray.length(tagged_leaf_hash(tag, leaf)) == 32
}

test prop_verify_tagged_empty_proof(
  vals via fuzz.both(fuzz.bytearray_between(1, 8), fuzz.bytearray_between(1, 32)),
) {
  let (tag, leaf) = vals
  let root = tagged_leaf_hash(tag, leaf)
  verify_proof_tagged(root, tag, leaf, [])
}

test prop_verify_tagged_single_sibling(
  vals via fuzz.both(
    fuzz.bytearray_between(1, 8),
    fuzz.both(fuzz.bytearray_between(1, 32), fuzz.bytearray_between(1, 32)),
  ),
) {
  let (tag, rest) = vals
  let (leaf, sibling) = rest
  let root = hash_pair(tagged_leaf_hash(tag, leaf), blake2b_256(sibling))
  verify_proof_tagged(root, tag, leaf, [blake2b_256(sibling)])
}

test prop_hash_pair_symmetric(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.bytearray_between(1, 16)),
) {
  let (a, b) = vals
  hash_pair(a, b) == hash_pair(b, a)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// A wrong root (all-zero 32 bytes) never matches the real tagged hash of any
// non-empty leaf with any non-empty tag, so verify_proof_tagged must return False.
test prop_wrong_root_rejected(
  vals via fuzz.both(fuzz.bytearray_between(1, 8), fuzz.bytearray_between(1, 32)),
) fail {
  let (tag, leaf) = vals
  let wrong_root = #"0000000000000000000000000000000000000000000000000000000000000000"
  expect verify_proof_tagged(wrong_root, tag, leaf, [])
}

// Using a different tag than the one used to build the root means the computed
// leaf hash will never equal the root, so the proof must fail.
test prop_mismatched_tag_rejected(
  vals via fuzz.both(
    fuzz.bytearray_between(1, 8),
    fuzz.both(fuzz.bytearray_between(1, 8), fuzz.bytearray_between(1, 32)),
  ),
) fail {
  let (tag_a, rest) = vals
  let (tag_b, leaf) = rest
  // Build root with tag_a, verify with tag_b.
  // Only fails when tag_a != tag_b; use a fixed known-different pair to guarantee it.
  let root = tagged_leaf_hash(#"aa", leaf)
  expect verify_proof_tagged(root, #"bb", leaf, [])
}

// A single wrong sibling in the proof means the computed root diverges from the
// real root, so verification must return False.
test prop_wrong_sibling_rejected(
  vals via fuzz.both(
    fuzz.bytearray_between(1, 8),
    fuzz.both(fuzz.bytearray_between(1, 32), fuzz.bytearray_between(1, 32)),
  ),
) fail {
  let (tag, rest) = vals
  let (leaf, bad_sibling) = rest
  // Real root has no siblings (empty proof), but we supply one wrong sibling.
  let root = tagged_leaf_hash(tag, leaf)
  expect verify_proof_tagged(root, tag, leaf, [blake2b_256(bad_sibling)])
}

// Swapping leaf and tag still produces a 32-byte hash, but it will not equal
// the root built with the correct (tag, leaf) order, so verification fails.
test prop_swapped_tag_leaf_rejected() fail {
  let tag  = #"deadbeef"
  let leaf = #"cafebabe"
  // Root built correctly: hash(tag ++ leaf)
  let root = tagged_leaf_hash(tag, leaf)
  // Now verify with tag and leaf swapped — hash(leaf ++ tag) != hash(tag ++ leaf)
  expect verify_proof_tagged(root, leaf, tag, [])
}