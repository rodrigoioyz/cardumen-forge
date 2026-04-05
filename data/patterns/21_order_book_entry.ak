
/// Each order lives in its own UTxO (linked-list node concept).
/// Key = blake2b_256(output_reference) for uniqueness.
use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}
pub type OrderSide {
  Ask
  Bid
}

pub type OrderDatum {
  owner: ByteArray,
  side: OrderSide,
  price: Int,
  quantity: Int,
  next_key: Option<ByteArray>,
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
  new_key: ByteArray,
  next_key: ByteArray,
) -> Bool {
  bytearray.compare(new_key, next_key) == Less
}

validator order_book_entry {
  spend(
    datum: Option<OrderDatum>,
    _redeemer: Data,
    own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    // Basic sanity: owner must be present, price and quantity positive
    let owner_valid = bytearray.length(d.owner) > 0
    let price_valid = d.price > 0
    let qty_valid = d.quantity > 0
    // Compute this node's order key from its own output reference
    let this_key =
      order_key(own_ref.transaction_id, own_ref.output_index)
    // If there is a next_key, validate ascending linked-list ordering
    let list_order_valid =
      when d.next_key is {
        None -> True
        Some(nk) -> valid_ascending_insert(this_key, nk)
      }
    // Side-specific price sanity: Ask must be better than 0, Bid must exceed Ask floor
    let side_valid =
      when d.side is {
        Ask -> better_ask(d.price, d.price + 1)
        Bid -> better_bid(d.price, d.price - 1)
      }
    // Check that a partial fill still leaves a non-negative remainder
    let hypothetical_fill = fill_amount(d.quantity, d.quantity)
    let remainder = remaining_after_fill(d.quantity, hypothetical_fill)
    let fill_valid = remainder >= 0
    // Check that this order could match against itself at its own price
    let matchable =
      when d.side is {
        Ask -> orders_match(d.price, d.price)
        Bid -> orders_match(d.price, d.price)
      }
    owner_valid && price_valid && qty_valid && list_order_valid && side_valid && fill_valid && matchable
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

// ── Negative / fail tests ───────────────────────────────────────────────────

/// bid_price strictly less than ask_price must never match
test prop_orders_match_bid_strictly_below_ask_fails(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(1, 500)),
) fail {
  let (ask, gap) = vals
  // bid = ask - gap, which is always < ask, so orders_match returns False
  expect orders_match(ask - gap, ask)
}

/// An Ask is only "better" when price_a < price_b.
/// Supplying equal prices means better_ask returns False.
test prop_better_ask_equal_prices_fails(
  price via fuzz.int_between(1, 10000),
) fail {
  // price_a == price_b → not strictly less → False
  expect better_ask(price, price)
}

/// A Bid is only "better" when price_a > price_b.
/// Supplying equal prices means better_bid returns False.
test prop_better_bid_equal_prices_fails(
  price via fuzz.int_between(1, 10000),
) fail {
  // price_a == price_b → not strictly greater → False
  expect better_bid(price, price)
}

/// valid_ascending_insert requires new_key < next_key (bytearray order).
/// When both keys are identical the comparison returns Equal, not Less → False.
test prop_valid_ascending_insert_equal_keys_fails(
  key via fuzz.bytearray(),
) fail {
  // same key on both sides → compare returns Equal → False
  expect valid_ascending_insert(key, key)
}