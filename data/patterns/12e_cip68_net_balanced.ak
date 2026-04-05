
use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/assets.{PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
const label_222: ByteArray = #"000de140"
const label_100: ByteArray = #"000643b0"

fn has_label(name: ByteArray, label: ByteArray) -> Bool {
  bytearray.length(name) >= 4 && bytearray.take(name, 4) == label
}

fn net_label_quantity(
  pairs: List<Pair<ByteArray, Int>>,
  label: ByteArray,
) -> Int {
  list.foldl(
    pairs,
    0,
    fn(p, acc) {
      let Pair(name, qty) = p
      if has_label(name, label) {
        acc + qty
      } else {
        acc
      }
    },
  )
}

/// Full update: both (222) and (100) nets must equal zero simultaneously
validator cip68_net_balanced {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens     = assets.tokens(self.mint, policy_id)
    let pairs_list = dict.to_pairs(tokens)
    net_label_quantity(pairs_list, label_222) == 0 && net_label_quantity(
      pairs_list,
      label_100,
    ) == 0
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_net_balanced_empty() {
  net_label_quantity([], label_222) == 0 && net_label_quantity([], label_100) == 0
}

test prop_net_balanced_222_cancels(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, -1), Pair(name, 1)]
  net_label_quantity(pairs, label_222) == 0
}

test prop_net_balanced_100_cancels(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_100, suffix)
  let pairs = [Pair(name, -1), Pair(name, 1)]
  net_label_quantity(pairs, label_100) == 0
}

test prop_net_balanced_cross_labels(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(-5, 5)),
) {
  let (suffix, qty) = vals
  let name222 = bytearray.concat(label_222, suffix)
  let name100 = bytearray.concat(label_100, suffix)
  let pairs   = [Pair(name222, qty)]
  net_label_quantity(pairs, label_100) == 0 && net_label_quantity(
    [Pair(name100, qty)],
    label_222,
  ) == 0
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// A single mint of a (222) token with a nonzero quantity must NOT net to zero.
test prop_222_nonzero_not_balanced(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(1, 1000)),
) fail {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, qty)]
  expect net_label_quantity(pairs, label_222) == 0
}

// A single mint of a (100) token with a nonzero quantity must NOT net to zero.
test prop_100_nonzero_not_balanced(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(1, 1000)),
) fail {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_100, suffix)
  let pairs = [Pair(name, qty)]
  expect net_label_quantity(pairs, label_100) == 0
}

// A name shorter than 4 bytes never satisfies has_label, but a (222)-prefixed
// name with a burn-only entry (negative net) must NOT be zero.
test prop_222_burn_only_not_balanced(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(1, 500)),
) fail {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_222, suffix)
  // negative net — should not equal zero
  let pairs = [Pair(name, -qty)]
  expect net_label_quantity(pairs, label_222) == 0
}

// Two entries that add up to a nonzero value must NOT net to zero.
test prop_222_unbalanced_pair_not_zero(
  vals via fuzz.both(
    fuzz.bytearray_between(1, 16),
    fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(1, 100)),
  ),
) fail {
  let (suffix, qtys) = vals
  let (qty_a, qty_b) = qtys
  let name  = bytearray.concat(label_222, suffix)
  // qty_a + qty_b is always >= 2, never zero
  let pairs = [Pair(name, qty_a), Pair(name, qty_b)]
  expect net_label_quantity(pairs, label_222) == 0
}