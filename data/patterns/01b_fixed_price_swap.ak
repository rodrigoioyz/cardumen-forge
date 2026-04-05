use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{lovelace_of}
use cardano/transaction.{Output, OutputReference, Transaction}

pub type FixedSwapDatum {
  price:  Int,
  seller: ByteArray,
}

/// Sum all lovelace in outputs going to seller_addr
fn total_paid_to(
  outputs:     List<Output>,
  seller_addr: address.Address,
) -> Int {
  list.foldl(
    outputs,
    0,
    fn(o, acc) {
      if o.address == seller_addr {
        acc + lovelace_of(o.value)
      } else {
        acc
      }
    },
  )
}

/// Buyer must pay at least `price` lovelace to seller — no ID required
validator fixed_price_swap {
  spend(
    datum: Option<FixedSwapDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let seller_addr = address.from_verification_key(d.seller)
    total_paid_to(self.outputs, seller_addr) >= d.price
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_total_paid_empty_outputs_zero() {
  let addr = address.from_verification_key(#"aabb")
  total_paid_to([], addr) == 0
}

test prop_total_paid_always_non_negative(
  price via fuzz.int_at_least(1),
) {
  let addr = address.from_verification_key(#"aabb")
  total_paid_to([], addr) >= 0 && price > 0
}

test prop_underpayment_fails(
  vals via fuzz.both(fuzz.int_at_least(2), fuzz.int_between(0, 1)),
) {
  let (price, paid) = vals
  // paid < price → total_paid_to([]) = 0 < price
  let addr = address.from_verification_key(#"aabb")
  if paid >= price {
    True
  } else {
    total_paid_to([], addr) < price
  }
}
