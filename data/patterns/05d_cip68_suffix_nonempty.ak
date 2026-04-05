use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

const label_222: ByteArray = #"000de140"

fn has_cip68_label(name: ByteArray, label: ByteArray) -> Bool {
  bytearray.length(name) >= 4 && bytearray.take(name, 4) == label
}

/// (222) tokens must have a non-empty suffix after the 4-byte label
fn has_nonempty_suffix(name: ByteArray) -> Bool {
  bytearray.length(name) > 4
}

/// All (222) tokens must carry a non-empty suffix
fn all_222_suffix_nonempty(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  list.all(
    dict.to_pairs(tokens),
    fn(p) {
      let Pair(name, _) = p
      if has_cip68_label(name, label_222) {
        has_nonempty_suffix(name)
      } else {
        True
      }
    },
  )
}

validator cip68_suffix_nonempty {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    all_222_suffix_nonempty(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_suffix_nonempty_empty_dict() {
  all_222_suffix_nonempty(dict.empty)
}

test prop_suffix_nonempty_ok(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_222, suffix)
  has_nonempty_suffix(name)
}

test prop_suffix_empty_fails() {
  !has_nonempty_suffix(label_222)
}

test prop_suffix_length_grows(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_222, suffix)
  bytearray.length(name) == 4 + bytearray.length(suffix)
}
