
/// Price improvement: buyer gets filled at a price better than or equal to their limit
use aiken/fuzz
use cardano/transaction.{Transaction, InlineDatum}
use cardano/assets
fn buyer_price_ok(execution_price: Int, limit_price: Int) -> Bool {
  execution_price <= limit_price
}

/// Seller also gets filled at or above their ask
fn seller_price_ok(execution_price: Int, ask_price: Int) -> Bool {
  execution_price >= ask_price
}

/// Both sides satisfied by execution price
fn prices_satisfied(
  execution_price: Int,
  buyer_limit: Int,
  seller_ask: Int,
) -> Bool {
  buyer_price_ok(execution_price, buyer_limit)
    && seller_price_ok(execution_price, seller_ask)
}

pub type OrderDatum {
  buyer_limit: Int,
  seller_ask: Int,
  execution_price: Int,
}

validator order_price_improvement {
  spend(
    datum: Option<OrderDatum>,
    _redeemer: Data,
    _output_ref: Data,
    _self: Transaction,
  ) {
    expect Some(d) = datum
    let buyer_ok = buyer_price_ok(d.execution_price, d.buyer_limit)
    let seller_ok = seller_price_ok(d.execution_price, d.seller_ask)
    let spread_valid = d.buyer_limit >= d.seller_ask
    let price_positive = d.execution_price > 0
    let combined = prices_satisfied(d.execution_price, d.buyer_limit, d.seller_ask)
    buyer_ok && seller_ok && spread_valid && price_positive && combined
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_midpoint_satisfies_both(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(501, 1000)),
) {
  let (ask, limit) = vals
  let mid = (ask + limit) / 2
  prices_satisfied(mid, limit, ask)
}

test prop_buyer_limit_violated(
  vals via fuzz.both(fuzz.int_between(101, 200), fuzz.int_between(1, 100)),
) {
  let (execution, limit) = vals
  !buyer_price_ok(execution, limit)
}

test prop_seller_ask_violated(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(101, 200)),
) {
  let (execution, ask) = vals
  !seller_price_ok(execution, ask)
}

test prop_equal_prices_satisfied(
  price via fuzz.int_between(1, 1000),
) {
  prices_satisfied(price, price, price)
}

// ── Negative (fail) property tests ───────────────────────────────────────────

// execution_price > limit_price guarantees buyer_price_ok returns False
test prop_fail_buyer_price_ok_when_execution_exceeds_limit(
  vals via fuzz.both(fuzz.int_between(101, 1000), fuzz.int_between(1, 100)),
) fail {
  let (execution, limit) = vals
  expect buyer_price_ok(execution, limit)
}

// execution_price < ask_price guarantees seller_price_ok returns False
test prop_fail_seller_price_ok_when_execution_below_ask(
  vals via fuzz.both(fuzz.int_between(1, 99), fuzz.int_between(100, 500)),
) fail {
  let (execution, ask) = vals
  expect seller_price_ok(execution, ask)
}

// execution_price above buyer_limit means prices_satisfied is always False
test prop_fail_prices_satisfied_execution_above_buyer_limit(
  vals via fuzz.both(fuzz.int_between(201, 500), fuzz.int_between(1, 200)),
) fail {
  let (execution, buyer_limit) = vals
  // seller_ask = 1 so seller side would pass, but buyer side fails
  expect prices_satisfied(execution, buyer_limit, 1)
}

// execution_price below seller_ask means prices_satisfied is always False
test prop_fail_prices_satisfied_execution_below_seller_ask(
  vals via fuzz.both(fuzz.int_between(1, 50), fuzz.int_between(51, 200)),
) fail {
  let (execution, seller_ask) = vals
  // buyer_limit = 1000 so buyer side would pass, but seller side fails
  expect prices_satisfied(execution, 1000, seller_ask)
}