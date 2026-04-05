use aiken/collection/list
use aiken/crypto.{blake2b_256}
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/transaction.{OutputReference, Transaction}

pub type NullifierDatum {
  merkle_root: ByteArray,
  nullifier:   ByteArray,
}

pub type NullifierRedeemer {
  leaf:      ByteArray,
  proof:     List<ByteArray>,
  secret:    ByteArray,
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

/// Nullifier: hash(leaf || secret) must equal the stored nullifier
fn valid_nullifier(leaf: ByteArray, secret: ByteArray, nullifier: ByteArray) -> Bool {
  blake2b_256(bytearray.concat(leaf, secret)) == nullifier
}

validator merkle_nullifier {
  spend(
    datum: Option<NullifierDatum>,
    redeemer: NullifierRedeemer,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    verify_proof(d.merkle_root, redeemer.leaf, redeemer.proof) && valid_nullifier(
      redeemer.leaf,
      redeemer.secret,
      d.nullifier,
    )
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_valid_nullifier_correct(
  vals via fuzz.both(fuzz.bytearray_between(1, 32), fuzz.bytearray_between(1, 32)),
) {
  let (leaf, secret) = vals
  let nullifier = blake2b_256(bytearray.concat(leaf, secret))
  valid_nullifier(leaf, secret, nullifier)
}

test prop_valid_nullifier_wrong_secret_fails(
  vals via fuzz.both(
    fuzz.bytearray_between(1, 16),
    fuzz.both(fuzz.bytearray_between(1, 16), fuzz.bytearray_between(1, 16)),
  ),
) fail {
  let (leaf, rest) = vals
  let (secret, wrong_secret) = rest
  if secret == wrong_secret {
    error
  } else {
    let nullifier = blake2b_256(bytearray.concat(leaf, secret))
    valid_nullifier(leaf, wrong_secret, nullifier)
  }
}

test prop_verify_empty_proof(leaf via fuzz.bytearray_between(1, 32)) {
  let root = blake2b_256(leaf)
  verify_proof(root, leaf, [])
}

test prop_hash_pair_symmetric(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.bytearray_between(1, 16)),
) {
  let (a, b) = vals
  hash_pair(a, b) == hash_pair(b, a)
}
