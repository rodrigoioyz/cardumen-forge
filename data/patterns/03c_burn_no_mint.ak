use aiken/collection/dict
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

/// No positive quantities (no minting) and at least one token present
fn no_mint_only_burn(tokens: dict.Dict<ByteArray, Int>) -> Bool {
  let vals = dict.values(tokens)
  !list.is_empty(vals) && list.all(vals, fn(qty) { qty <= 0 })
}

validator burn_no_mint {
  mint(
    _redeemer: Data,
    policy_id: PolicyId,
    self: Transaction,
  ) -> Bool {
    let tokens = assets.tokens(self.mint, policy_id)
    no_mint_only_burn(tokens)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_no_mint_empty_false() {
  !no_mint_only_burn(dict.empty)
}

test prop_no_mint_negative_ok(name via fuzz.bytearray_between(1, 16)) {
  let d = dict.empty |> dict.insert(name, -1)
  no_mint_only_burn(d)
}

test prop_no_mint_zero_ok(name via fuzz.bytearray_between(1, 16)) {
  let d = dict.empty |> dict.insert(name, 0)
  no_mint_only_burn(d)
}

test prop_no_mint_positive_fails(
  vals via fuzz.both(fuzz.bytearray_between(1, 16), fuzz.int_at_least(1)),
) {
  let (name, qty) = vals
  let d = dict.empty |> dict.insert(name, qty)
  !no_mint_only_burn(d)
}
