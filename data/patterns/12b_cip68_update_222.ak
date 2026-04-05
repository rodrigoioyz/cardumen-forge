
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

/// Update user token: burn old (222) mint new (222) → net=0; (100) must not appear
validator cip68_update_222 {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens     = assets.tokens(self.mint, policy_id)
    let pairs_list = dict.to_pairs(tokens)
    let no_ref_tokens =
      list.all(
        pairs_list,
        fn(p) { !has_label(p.1st, label_100) },
      )
    let net_user = net_label_quantity(pairs_list, label_222)
    no_ref_tokens && net_user == 0
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_net_222_empty() {
  net_label_quantity([], label_222) == 0
}

test prop_net_222_burn_mint_cancels(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, -1), Pair(name, 1)]
  net_label_quantity(pairs, label_222) == 0
}

test prop_net_222_ignores_100(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(-5, 5)),
) {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_100, suffix)
  let pairs = [Pair(name, qty)]
  net_label_quantity(pairs, label_222) == 0
}

test prop_net_222_single_mint(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, 1)]
  net_label_quantity(pairs, label_222) == 1
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// A name shorter than 4 bytes can never match a 4-byte label,
// so has_label must always return False for such inputs.
test prop_has_label_too_short(
  short via fuzz.bytearray_between(0, 3),
) fail {
  expect has_label(short, label_222)
}

// A single unbalanced mint (qty > 0) means net != 0, so the equality check fails.
// We verify by asserting net_label_quantity == 0, which is False for qty >= 1.
test prop_net_222_nonzero_single_positive(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(1, 100)),
) fail {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, qty)]
  expect net_label_quantity(pairs, label_222) == 0
}

// A single unbalanced burn (qty < 0) also yields net != 0.
test prop_net_222_nonzero_single_negative(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(-100, -1)),
) fail {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, qty)]
  expect net_label_quantity(pairs, label_222) == 0
}

// has_label returns False when the label prefix does not match,
// even if the bytearray is long enough (>= 4 bytes).
// We use label_100 as the name prefix and check against label_222 — always False.
test prop_has_label_wrong_prefix(
  suffix via fuzz.bytearray_between(1, 16),
) fail {
  let name = bytearray.concat(label_100, suffix)
  expect has_label(name, label_222)
}