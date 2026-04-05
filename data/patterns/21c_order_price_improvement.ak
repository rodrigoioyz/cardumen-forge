use aiken/fuzz

/// Price improvement: buyer gets filled at a price better than or equal to their limit
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
  buyer_limit:     Int,
  seller_ask:      Int,
) -> Bool {
  buyer_price_ok(execution_price, buyer_limit)
    && seller_price_ok(execution_price, seller_ask)
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
