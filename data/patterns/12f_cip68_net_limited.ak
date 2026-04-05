
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

/// Net minted (222) tokens must not exceed a per-tx cap
fn within_mint_cap(pairs: List<Pair<ByteArray, Int>>, cap: Int) -> Bool {
  let net = net_label_quantity(pairs, label_222)
  net > 0 && net <= cap
}

validator cip68_net_limited {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens     = assets.tokens(self.mint, policy_id)
    let pairs_list = dict.to_pairs(tokens)
    within_mint_cap(pairs_list, 5)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_within_cap_one(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, 1)]
  within_mint_cap(pairs, 5)
}

test prop_within_cap_at_limit(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, 5)]
  within_mint_cap(pairs, 5)
}

test prop_within_cap_exceeds_limit(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, 6)]
  !within_mint_cap(pairs, 5)
}

test prop_net_label_ignores_100(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(-5, 5)),
) {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_100, suffix)
  let pairs = [Pair(name, qty)]
  net_label_quantity(pairs, label_222) == 0
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// Empty pair list has net=0 which is not >0, so within_mint_cap returns False
test prop_empty_pairs_rejected(
  cap via fuzz.int_between(1, 100),
) fail {
  expect within_mint_cap([], cap)
}

// Quantity exceeds cap → within_mint_cap returns False
test prop_over_cap_rejected(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(6, 1000)),
) fail {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, qty)]
  expect within_mint_cap(pairs, 5)
}

// Zero quantity net=0 → within_mint_cap returns False (net must be >0)
test prop_zero_quantity_rejected(
  suffix via fuzz.bytearray_between(1, 16),
) fail {
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, 0)]
  expect within_mint_cap(pairs, 5)
}

// Negative quantity net<0 → within_mint_cap returns False (net must be >0)
test prop_negative_quantity_rejected(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(-500, -1)),
) fail {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, qty)]
  expect within_mint_cap(pairs, 5)
}