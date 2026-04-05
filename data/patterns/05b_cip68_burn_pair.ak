use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

const label_222: ByteArray = #"000de140"
const label_100: ByteArray = #"000643b0"

fn has_cip68_label(name: ByteArray, label: ByteArray) -> Bool {
  bytearray.length(name) >= 4 && bytearray.take(name, 4) == label
}

fn base_name(name: ByteArray) -> ByteArray {
  bytearray.drop(name, 4)
}

/// For every (222) token burned, the matching (100) reference must also be burned
fn burn_pairs_balanced(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  list.all(
    dict.to_pairs(tokens),
    fn(p) {
      let Pair(name, qty) = p
      if has_cip68_label(name, label_222) {
        qty < 0 && {
          let ref_name = bytearray.concat(label_100, base_name(name))
          dict.get(tokens, ref_name) == Some(qty)
        }
      } else {
        True
      }
    },
  )
}

validator cip68_burn_pair {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    burn_pairs_balanced(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_burn_pair_empty() {
  burn_pairs_balanced(dict.empty)
}

test prop_base_name_roundtrip(suffix via fuzz.bytearray_between(1, 28)) {
  let full = bytearray.concat(label_222, suffix)
  base_name(full) == suffix
}

test prop_has_label_222(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_222, suffix)
  has_cip68_label(name, label_222)
}

test prop_has_label_too_short(name via fuzz.bytearray_between(0, 3)) {
  !has_cip68_label(name, label_222)
}
