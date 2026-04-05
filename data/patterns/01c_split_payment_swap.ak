use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{lovelace_of}
use cardano/transaction.{Output, OutputReference, Transaction}

pub type SplitSwapDatum {
  price:        Int,
  seller:       ByteArray,
  fee_receiver: ByteArray,
  fee_percent:  Int,
}

/// Lovelace going to a specific address
fn lovelace_to(outputs: List<Output>, addr: address.Address) -> Int {
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

/// Fee portion out of total price (integer division)
fn fee_amount(price: Int, fee_percent: Int) -> Int {
  price * fee_percent / 100
}

/// Seller receives price minus fee; fee_receiver gets the fee
validator split_payment_swap {
  spend(
    datum: Option<SplitSwapDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let seller_addr   = address.from_verification_key(d.seller)
    let fee_addr      = address.from_verification_key(d.fee_receiver)
    let fee           = fee_amount(d.price, d.fee_percent)
    let seller_share  = d.price - fee
    lovelace_to(self.outputs, seller_addr) >= seller_share
      && lovelace_to(self.outputs, fee_addr) >= fee
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_fee_zero_percent(price via fuzz.int_at_least(1)) {
  fee_amount(price, 0) == 0
}

test prop_fee_full_percent(price via fuzz.int_at_least(1)) {
  fee_amount(price, 100) == price
}

test prop_fee_within_price(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(0, 100)),
) {
  let (price, pct) = vals
  let fee = fee_amount(price, pct)
  fee >= 0 && fee <= price
}

test prop_seller_share_non_negative(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(0, 100)),
) {
  let (price, pct) = vals
  price - fee_amount(price, pct) >= 0
}
