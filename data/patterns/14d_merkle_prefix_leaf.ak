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
    verify_proof_tagged(d.merkle_root, d.domain_tag, redeemer.leaf, redeemer.proof)
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
