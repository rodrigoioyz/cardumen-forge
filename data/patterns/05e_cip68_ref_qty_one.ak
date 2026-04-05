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
    all_ref_qty_one(tokens)
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
