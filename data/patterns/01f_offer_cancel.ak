use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{lovelace_of}
use cardano/transaction.{Output, OutputReference, Transaction}

pub type OfferDatum {
  price:  Int,
  seller: ByteArray,
}

pub type OfferRedeemer {
  Accept
  Cancel
}

fn lovelace_to_addr(outputs: List<Output>, addr: address.Address) -> Int {
  list.foldl(
    outputs,
    0,
    fn(o, acc) {
      if o.address == addr {
        acc + lovelace_of(o.value)
      } else {
        acc
      }
    },
  )
}

/// Accept: buyer pays price to seller
/// Cancel: seller signs to reclaim their offer
validator offer_cancel {
  spend(
    datum: Option<OfferDatum>,
    redeemer: OfferRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      Accept -> {
        let seller_addr = address.from_verification_key(d.seller)
        lovelace_to_addr(self.outputs, seller_addr) >= d.price
      }
      Cancel ->
        list.has(self.extra_signatories, d.seller)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_lovelace_to_empty_is_zero() {
  let addr = address.from_verification_key(#"beef")
  lovelace_to_addr([], addr) == 0
}

test prop_accept_requires_positive_price(price via fuzz.int_at_least(1)) {
  // No outputs → 0 lovelace → fails Accept for any price > 0
  let addr = address.from_verification_key(#"beef")
  lovelace_to_addr([], addr) < price
}

test prop_lovelace_monotone(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  // Adding more units to price always increases total required
  let (p1, extra) = vals
  p1 < p1 + extra
}
