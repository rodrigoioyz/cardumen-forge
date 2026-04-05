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

/// Token name must carry either the (222) or (100) CIP-68 label
fn is_known_label(name: ByteArray) -> Bool {
  has_cip68_label(name, label_222) || has_cip68_label(name, label_100)
}

/// All minted token names must carry a known CIP-68 label
fn all_known_labels(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  list.all(
    dict.to_pairs(tokens),
    fn(p) {
      let Pair(name, _) = p
      is_known_label(name)
    },
  )
}

validator cip68_label_only {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    all_known_labels(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_label_only_empty() {
  all_known_labels(dict.empty)
}

test prop_label_222_accepted(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_222, suffix)
  is_known_label(name)
}

test prop_label_100_accepted(suffix via fuzz.bytearray_between(1, 28)) {
  let name = bytearray.concat(label_100, suffix)
  is_known_label(name)
}

test prop_no_label_rejected(name via fuzz.bytearray_between(4, 32)) {
  let has222 = has_cip68_label(name, label_222)
  let has100 = has_cip68_label(name, label_100)
  if has222 || has100 {
    True
  } else {
    !is_known_label(name)
  }
}
