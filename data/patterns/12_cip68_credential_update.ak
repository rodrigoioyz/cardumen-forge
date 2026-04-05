
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

/// Net quantity for tokens with given label prefix
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

/// Update: burn old (100) and mint new (100) → net = 0 for label_100
/// User token (222) must NOT appear in mint at all
validator cip68_credential_update {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens     = assets.tokens(self.mint, policy_id)
    let pairs_list = dict.to_pairs(tokens)
    // No (222) tokens in this mint
    let no_user_tokens =
      list.all(pairs_list, fn(p) { !has_label(p.1st, label_222) })
    // Net (100) quantity is zero (burn one, mint one)
    let net_ref = net_label_quantity(pairs_list, label_100)
    no_user_tokens && net_ref == 0
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_net_label_empty() {
  net_label_quantity([], label_100) == 0
}

test prop_net_label_burn_mint_cancels(suffix via fuzz.bytearray_between(1, 16)) {
  let name   = bytearray.concat(label_100, suffix)
  let pairs  = [Pair(name, -1), Pair(name, 1)]
  net_label_quantity(pairs, label_100) == 0
}

test prop_net_label_ignores_other_labels(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(-5, 5)),
) {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, qty)]
  net_label_quantity(pairs, label_100) == 0
}

test prop_net_label_non_zero_single_burn(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_100, suffix)
  let pairs = [Pair(name, -1)]
  net_label_quantity(pairs, label_100) == -1
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// has_label must reject names shorter than 4 bytes — length 0..3 always too short
test prop_has_label_rejects_short_name(
  name via fuzz.bytearray_between(0, 3),
) fail {
  expect has_label(name, label_100)
}

// A single label_100 token with non-zero quantity gives net != 0;
// specifically a positive quantity means net_label_quantity > 0, not == 0.
// We check that the net equals some non-zero value by expecting net == 0 to fail.
test prop_net_label_nonzero_when_only_mint(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(1, 100)),
) fail {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_100, suffix)
  let pairs = [Pair(name, qty)]
  // net is qty (>= 1), so == 0 is False → expect fails
  expect net_label_quantity(pairs, label_100) == 0
}

// has_label must reject a name whose first 4 bytes are label_222, not label_100
test prop_has_label_wrong_label_rejected(
  suffix via fuzz.bytearray_between(1, 16),
) fail {
  let name = bytearray.concat(label_222, suffix)
  // name has label_222 prefix, so has_label(name, label_100) is False
  expect has_label(name, label_100)
}

// net_label_quantity with only a burn (qty = -k) for label_100 is negative, not zero
test prop_net_label_only_burn_nonzero(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(1, 100)),
) fail {
  let (suffix, burn_qty) = vals
  let name  = bytearray.concat(label_100, suffix)
  let pairs = [Pair(name, -burn_qty)]
  // net is -burn_qty (<= -1), so == 0 is False → expect fails
  expect net_label_quantity(pairs, label_100) == 0
}