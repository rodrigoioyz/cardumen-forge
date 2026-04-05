
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

/// Pure mint: net (222) must be > 0 and net (100) must be > 0
validator cip68_net_positive {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens     = assets.tokens(self.mint, policy_id)
    let pairs_list = dict.to_pairs(tokens)
    net_label_quantity(pairs_list, label_222) > 0 && net_label_quantity(
      pairs_list,
      label_100,
    ) > 0
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_net_positive_222_mint(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, 1)]
  net_label_quantity(pairs, label_222) > 0
}

test prop_net_positive_burn_not_positive(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, -1)]
  !(net_label_quantity(pairs, label_222) > 0)
}

test prop_net_positive_empty_not_positive() {
  !(net_label_quantity([], label_222) > 0)
}

test prop_net_positive_ignores_other(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(1, 10)),
) {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_100, suffix)
  let pairs = [Pair(name, qty)]
  net_label_quantity(pairs, label_222) == 0
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Burning (negative qty) label_222 tokens must never yield a positive net
test prop_fail_burn_222_is_positive(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(1, 1000)),
) fail {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, -qty)]
  expect net_label_quantity(pairs, label_222) > 0
}

/// An empty pair list must never yield a positive net for label_100
test prop_fail_empty_pairs_100_positive() fail {
  expect net_label_quantity([], label_100) > 0
}

/// Tokens with label_100 must not contribute to the label_222 net, so
/// querying label_222 over a list of only label_100 tokens must never be > 0
test prop_fail_100_tokens_counted_as_222(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(1, 500)),
) fail {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_100, suffix)
  let pairs = [Pair(name, qty)]
  expect net_label_quantity(pairs, label_222) > 0
}

/// A short name (fewer than 4 bytes) must never match any label, so net must
/// never be positive regardless of quantity
test prop_fail_short_name_matches_label(
  qty via fuzz.int_between(1, 1000),
) fail {
  // #"aabb" is only 2 bytes — too short for has_label to match
  let pairs = [Pair(#"aabb", qty)]
  expect net_label_quantity(pairs, label_222) > 0
}