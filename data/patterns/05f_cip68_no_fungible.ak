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

fn is_cip68_token(name: ByteArray) -> Bool {
  has_cip68_label(name, label_222) || has_cip68_label(name, label_100)
}

/// No CIP-68 labeled token may have |qty| > 1 (no fungible copies)
fn no_cip68_fungible(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  list.all(
    dict.to_pairs(tokens),
    fn(p) {
      let Pair(name, qty) = p
      if is_cip68_token(name) {
        qty == 1 || qty == -1
      } else {
        True
      }
    },
  )
}

validator cip68_no_fungible {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    no_cip68_fungible(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_no_fungible_empty() {
  no_cip68_fungible(dict.empty)
}

test prop_no_fungible_qty_one_ok(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_222, suffix)
  let tokens = dict.empty |> dict.insert(name, 1)
  no_cip68_fungible(tokens)
}

test prop_no_fungible_burn_ok(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_100, suffix)
  let tokens = dict.empty |> dict.insert(name, -1)
  no_cip68_fungible(tokens)
}

test prop_no_fungible_qty_two_fails(
  vals via fuzz.both(fuzz.bytearray_between(1, 28), fuzz.int_at_least(2)),
) {
  let (suffix, qty) = vals
  let name = bytearray.concat(label_222, suffix)
  let tokens = dict.empty |> dict.insert(name, qty)
  !no_cip68_fungible(tokens)
}
