
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

/// Token name must carry either the (222) or (100) CIP-68 label
fn is_known_label(name: ByteArray) -> Bool {
  has_cip68_label(name, label_222) || has_cip68_label(name, label_100)
}

/// All minted token names must carry a known CIP-68 label
fn all_known_labels(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  list.all(
    dict.to_pairs(tokens),
    fn(p) {
      let Pair(name, _) = p
      is_known_label(name)
    },
  )
}

validator cip68_label_only {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    let token_count = dict.size(tokens)
    let at_least_one = token_count > 0
    let all_valid_labels = all_known_labels(tokens)
    let no_zero_amounts =
      list.all(
        dict.to_pairs(tokens),
        fn(p) {
          let Pair(name, qty) = p
          is_known_label(name) && qty != 0
        },
      )
    at_least_one && all_valid_labels && no_zero_amounts
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_label_only_empty() {
  all_known_labels(dict.empty)
}

test prop_label_222_accepted(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_222, suffix)
  is_known_label(name)
}

test prop_label_100_accepted(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_100, suffix)
  is_known_label(name)
}

test prop_no_label_rejected(name via fuzz.bytearray_between(4, 32)) {
  let has222 = has_cip68_label(name, label_222)
  let has100 = has_cip68_label(name, label_100)
  if has222 || has100 {
    True
  } else {
    !is_known_label(name)
  }
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// A name shorter than 4 bytes can never carry a valid CIP-68 label prefix,
// so is_known_label must always return False for it.
test prop_short_name_rejected(name via fuzz.bytearray_between(0, 3)) fail {
  expect is_known_label(name)
}

// A name whose first 4 bytes are not label_222 (#"000de140") and not
// label_100 (#"000643b0") must be rejected.  We force the first byte to
// #"ff" which differs from both labels' leading byte (#"00"), guaranteeing
// the prefix never matches regardless of the remaining bytes.
test prop_wrong_prefix_rejected(suffix via fuzz.bytearray_between(3, 28)) fail {
  let bad_name = bytearray.concat(#"ff", suffix)
  expect is_known_label(bad_name)
}

// has_cip68_label with a label that is not label_222/label_100 must reject
// a name that only carries label_222, confirming the label argument is
// actually checked.  We use #"deadbeef" as the wrong label.
test prop_wrong_label_not_matched(suffix via fuzz.bytearray_between(1, 28)) fail {
  let name = bytearray.concat(label_222, suffix)
  expect has_cip68_label(name, #"deadbeef")
}

// all_known_labels must return False when the dict contains a token whose
// name has an invalid prefix.  We insert a single entry with a name that
// starts with #"ff" (never a valid CIP-68 label).
test prop_dict_with_bad_label_rejected(suffix via fuzz.bytearray_between(3, 28)) fail {
  let bad_name = bytearray.concat(#"ff", suffix)
  let tokens = dict.insert(dict.empty, bad_name, 1)
  expect all_known_labels(tokens)
}