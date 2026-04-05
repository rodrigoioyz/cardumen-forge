
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
    // Must mint at least one token
    let token_count = dict.size(tokens)
    expect token_count > 0
    // Every minted name must carry either a (222) or (100) label
    let all_labelled =
      list.all(
        dict.to_pairs(tokens),
        fn(p) {
          let Pair(name, _qty) = p
          has_cip68_label(name, label_222) || has_cip68_label(name, label_100)
        },
      )
    expect all_labelled
    // Every (222) user token must have a paired (100) reference token
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A name shorter than 4 bytes can never carry a CIP-68 label — has_cip68_label
/// must return False, so `expect` always fails.
test prop_fail_label_on_short_name(
  name via fuzz.bytearray_between(0, 3),
) fail {
  expect has_cip68_label(name, label_222)
}

/// A name whose first 4 bytes differ from label_222 must be rejected.
/// We guarantee a mismatch by using label_100 as the prefix.
test prop_fail_wrong_label_prefix(
  suffix via fuzz.bytearray_between(0, 28),
) fail {
  let name = bytearray.concat(label_100, suffix)
  expect has_cip68_label(name, label_222)
}

/// A (222) token minted with qty=1 but without its paired (100) token means
/// pairs_balanced must return False.  We build a dict containing only the
/// user token and no reference token.
test prop_fail_unpaired_222_token(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  let user_name = bytearray.concat(label_222, suffix)
  let tokens = dict.insert(dict.empty, user_name, 1)
  expect pairs_balanced(tokens)
}

/// A (222) token minted with qty != 1 (e.g. 2) must be rejected by
/// pairs_balanced even when the matching (100) token is present.
test prop_fail_222_qty_not_one(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  let user_name = bytearray.concat(label_222, suffix)
  let ref_name = bytearray.concat(label_100, suffix)
  let tokens =
    dict.empty
      |> dict.insert(user_name, 2)
      |> dict.insert(ref_name, 1)
  expect pairs_balanced(tokens)
}