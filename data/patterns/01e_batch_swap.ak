use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{lovelace_of}
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}

pub type BatchSwapDatum {
  price_per_unit: Int,
  units:          Int,
  seller:         ByteArray,
  order_id:       ByteArray,
}

/// Count outputs to seller that carry the matching order_id tag
fn tagged_lovelace(
  outputs:     List<Output>,
  seller_addr: address.Address,
  order_id:    ByteArray,
) -> Int {
  list.foldl(
    outputs,
    0,
    fn(o, acc) {
      if o.address == seller_addr {
        when o.datum is {
          InlineDatum(raw) -> {
            expect tag: ByteArray = raw
            if tag == order_id {
              acc + lovelace_of(o.value)
            } else {
              acc
            }
          }
          _ -> acc
        }
      } else {
        acc
      }
    },
  )
}

/// Total price = price_per_unit * units
fn total_price(price_per_unit: Int, units: Int) -> Int {
  price_per_unit * units
}

validator batch_swap {
  spend(
    datum: Option<BatchSwapDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let seller_addr = address.from_verification_key(d.seller)
    let required    = total_price(d.price_per_unit, d.units)
    tagged_lovelace(self.outputs, seller_addr, d.order_id) >= required
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_total_price_zero_units(price via fuzz.int_at_least(1)) {
  total_price(price, 0) == 0
}

test prop_total_price_one_unit(price via fuzz.int_at_least(1)) {
  total_price(price, 1) == price
}

test prop_total_price_commutative(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (a, b) = vals
  total_price(a, b) == total_price(b, a)
}

test prop_tagged_lovelace_empty(order_id via fuzz.bytearray_between(1, 16)) {
  let addr = address.from_verification_key(#"aabb")
  tagged_lovelace([], addr, order_id) == 0
}
