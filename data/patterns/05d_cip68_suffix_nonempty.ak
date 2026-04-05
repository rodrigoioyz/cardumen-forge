
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
    let pairs = dict.to_pairs(tokens)
    let has_any_minted = list.length(pairs) > 0
    let all_suffixes_valid = all_222_suffix_nonempty(tokens)
    let all_222_have_label =
      list.all(
        pairs,
        fn(p) {
          let Pair(name, _) = p
          if has_cip68_label(name, label_222) {
            has_nonempty_suffix(name)
          } else {
            True
          }
        },
      )
    has_any_minted && all_suffixes_valid && all_222_have_label
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// The bare 4-byte label with no suffix must always be rejected by has_nonempty_suffix
test prop_bare_label_rejected() fail {
  expect has_nonempty_suffix(label_222)
}

/// Any bytearray of length <= 4 must be rejected by has_nonempty_suffix
test prop_short_name_rejected(
  name via fuzz.bytearray_between(0, 4),
) fail {
  expect has_nonempty_suffix(name)
}

/// A dict containing the bare 4-byte label (no suffix) as a key must fail
/// all_222_suffix_nonempty because it has the CIP-68 label but no suffix
test prop_dict_bare_label_rejected() fail {
  let tokens =
    dict.from_ascending_pairs([Pair(label_222, 1)])
  expect all_222_suffix_nonempty(tokens)
}

/// has_cip68_label must reject any name shorter than 4 bytes
test prop_short_name_no_label(
  name via fuzz.bytearray_between(0, 3),
) fail {
  expect has_cip68_label(name, label_222)
}