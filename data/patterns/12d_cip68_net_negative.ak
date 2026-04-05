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

/// Pure burn: net (222) must be < 0 and net (100) must be < 0
validator cip68_net_negative {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens     = assets.tokens(self.mint, policy_id)
    let pairs_list = dict.to_pairs(tokens)
    net_label_quantity(pairs_list, label_222) < 0 && net_label_quantity(
      pairs_list,
      label_100,
    ) < 0
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_net_negative_222_burn(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, -1)]
  net_label_quantity(pairs, label_222) < 0
}

test prop_net_negative_mint_not_negative(suffix via fuzz.bytearray_between(1, 16)) {
  let name  = bytearray.concat(label_222, suffix)
  let pairs = [Pair(name, 1)]
  !(net_label_quantity(pairs, label_222) < 0)
}

test prop_net_negative_empty_not_negative() {
  !(net_label_quantity([], label_222) < 0)
}

test prop_net_negative_ignores_other(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_between(-10, -1)),
) {
  let (suffix, qty) = vals
  let name  = bytearray.concat(label_100, suffix)
  let pairs = [Pair(name, qty)]
  net_label_quantity(pairs, label_222) == 0
}
