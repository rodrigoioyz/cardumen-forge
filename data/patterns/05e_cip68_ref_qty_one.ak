
use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}
const label_100: ByteArray = #"000643b0"

fn has_cip68_label(name: ByteArray, label: ByteArray) -> Bool {
  bytearray.length(name) >= 4 && bytearray.take(name, 4) == label
}

/// All (100) reference tokens must be minted with qty exactly 1
fn all_ref_qty_one(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  list.all(
    dict.to_pairs(tokens),
    fn(p) {
      let Pair(name, qty) = p
      if has_cip68_label(name, label_100) {
        qty == 1
      } else {
        True
      }
    },
  )
}

validator cip68_ref_qty_one {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    let pairs = dict.to_pairs(tokens)
    let has_any_ref =
      list.any(pairs, fn(p) {
        let Pair(name, _qty) = p
        has_cip68_label(name, label_100)
      })
    let ref_qty_valid = all_ref_qty_one(tokens)
    let no_zero_qty =
      list.all(pairs, fn(p) {
        let Pair(_name, qty) = p
        qty != 0
      })
    has_any_ref && ref_qty_valid && no_zero_qty
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_ref_qty_one_empty() {
  all_ref_qty_one(dict.empty)
}

test prop_ref_qty_one_ok(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_100, suffix)
  let tokens = dict.empty |> dict.insert(name, 1)
  all_ref_qty_one(tokens)
}

test prop_ref_qty_two_fails(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_100, suffix)
  let tokens = dict.empty |> dict.insert(name, 2)
  !all_ref_qty_one(tokens)
}

test prop_ref_qty_negative_fails(
  vals via fuzz.both(fuzz.bytearray_between(1, 28), fuzz.int_at_least(1)),
) {
  let (suffix, amt) = vals
  let name = bytearray.concat(label_100, suffix)
  let tokens = dict.empty |> dict.insert(name, -amt)
  !all_ref_qty_one(tokens)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

// A ref token minted with qty=2 must be rejected by all_ref_qty_one
test prop_ref_qty_two_rejected(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  let name = bytearray.concat(label_100, suffix)
  let tokens = dict.empty |> dict.insert(name, 2)
  expect all_ref_qty_one(tokens)
}

// A ref token minted with any qty >= 2 must be rejected
test prop_ref_qty_gt_one_rejected(
  vals via fuzz.both(fuzz.bytearray_between(1, 28), fuzz.int_between(2, 1000)),
) fail {
  let (suffix, qty) = vals
  let name = bytearray.concat(label_100, suffix)
  let tokens = dict.empty |> dict.insert(name, qty)
  expect all_ref_qty_one(tokens)
}

// A ref token minted with any negative qty must be rejected
test prop_ref_qty_negative_rejected(
  vals via fuzz.both(fuzz.bytearray_between(1, 28), fuzz.int_at_least(1)),
) fail {
  let (suffix, amt) = vals
  let name = bytearray.concat(label_100, suffix)
  let tokens = dict.empty |> dict.insert(name, -amt)
  expect all_ref_qty_one(tokens)
}

// A ref token minted with qty=0 must be rejected
test prop_ref_qty_zero_rejected(
  suffix via fuzz.bytearray_between(1, 28),
) fail {
  let name = bytearray.concat(label_100, suffix)
  let tokens = dict.empty |> dict.insert(name, 0)
  expect all_ref_qty_one(tokens)
}