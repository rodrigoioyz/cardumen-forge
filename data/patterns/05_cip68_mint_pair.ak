use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

const label_222: ByteArray = #"000de140"
const label_100: ByteArray = #"000643b0"

/// Check that a token name carries the given 4-byte CIP-0068 label
fn has_cip68_label(name: ByteArray, label: ByteArray) -> Bool {
  bytearray.length(name) >= 4 && bytearray.take(name, 4) == label
}

/// Strip label prefix to get the base name
fn base_name(name: ByteArray) -> ByteArray {
  bytearray.drop(name, 4)
}

/// For every (222) token minted with qty=1, a matching (100) must also be minted qty=1
fn pairs_balanced(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  let pairs_list = dict.to_pairs(tokens)
  list.all(
    pairs_list,
    fn(p) {
      let Pair(name, qty) = p
      if has_cip68_label(name, label_222) {
        qty == 1 && {
          let ref_name = bytearray.concat(label_100, base_name(name))
          dict.get(tokens, ref_name) == Some(1)
        }
      } else {
        True
      }
    },
  )
}

validator cip68_mint {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    pairs_balanced(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_has_cip68_label_correct() {
  has_cip68_label(#"000de140aabb", label_222)
}

test prop_has_cip68_label_wrong_prefix() {
  !has_cip68_label(#"000de141aabb", label_222)
}

test prop_has_cip68_label_too_short(name via fuzz.bytearray_between(0, 3)) {
  !has_cip68_label(name, label_222)
}

test prop_has_cip68_label_exact_length() {
  has_cip68_label(label_222, label_222)
}

test prop_pairs_balanced_empty() {
  pairs_balanced(dict.empty)
}

test prop_base_name_roundtrip(suffix via fuzz.bytearray_between(1, 28)) {
  let full = bytearray.concat(label_222, suffix)
  base_name(full) == suffix
}
