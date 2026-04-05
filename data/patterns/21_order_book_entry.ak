use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}

/// Each order lives in its own UTxO (linked-list node concept).
/// Key = blake2b_256(output_reference) for uniqueness.
pub type OrderSide {
  Ask
  Bid
}

pub type OrderDatum {
  owner:      ByteArray,
  side:       OrderSide,
  price:      Int,
  quantity:   Int,
  next_key:   Option<ByteArray>,
}

/// An Ask at price_a is better (lower) than one at price_b
fn better_ask(price_a: Int, price_b: Int) -> Bool {
  price_a < price_b
}

/// A Bid at price_a is better (higher) than one at price_b
fn better_bid(price_a: Int, price_b: Int) -> Bool {
  price_a > price_b
}

/// Orders match when bid_price >= ask_price
fn orders_match(bid_price: Int, ask_price: Int) -> Bool {
  bid_price >= ask_price
}

/// Amount filled = min(bid_qty, ask_qty)
fn fill_amount(bid_qty: Int, ask_qty: Int) -> Int {
  if bid_qty <= ask_qty {
    bid_qty
  } else {
    ask_qty
  }
}

/// Remaining quantity after partial fill
fn remaining_after_fill(order_qty: Int, filled: Int) -> Int {
  order_qty - filled
}

/// Order key from output reference (for linked-list node ordering)
fn order_key(ref_bytes: ByteArray, output_index: Int) -> ByteArray {
  bytearray.concat(
    ref_bytes,
    bytearray.from_int_big_endian(output_index, 2),
  )
}

/// Valid ascending insertion: new key must be < existing next key
fn valid_ascending_insert(
  new_key:  ByteArray,
  next_key: ByteArray,
) -> Bool {
  bytearray.compare(new_key, next_key) == Less
}

validator order_book_entry {
  spend(
    datum: Option<OrderDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    d.quantity > 0 && d.price > 0
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_orders_match_bid_gte_ask(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(0, 50)),
) {
  let (ask, premium) = vals
  orders_match(ask + premium, ask)
}

test prop_orders_no_match_bid_lt_ask(
  vals via fuzz.both(fuzz.int_between(2, 100), fuzz.int_between(1, 50)),
) {
  let (ask, discount) = vals
  !orders_match(ask - discount, ask)
}

test prop_fill_amount_is_minimum(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (bid_qty, ask_qty) = vals
  let filled = fill_amount(bid_qty, ask_qty)
  filled <= bid_qty && filled <= ask_qty
}

test prop_remaining_after_full_fill(qty via fuzz.int_at_least(1)) {
  remaining_after_fill(qty, qty) == 0
}
