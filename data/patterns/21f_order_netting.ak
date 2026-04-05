use aiken/fuzz

/// Net position after matching N buy orders against M sell orders
/// Simplified: single buyer/seller, net_qty = buy_qty - sell_qty
fn net_position(buy_qty: Int, sell_qty: Int) -> Int {
  buy_qty - sell_qty
}

/// Settlement amount for net position at clearing price
fn settlement_amount(net_qty: Int, clearing_price: Int) -> Int {
  if net_qty >= 0 {
    net_qty * clearing_price
  } else {
    -net_qty * clearing_price
  }
}

/// Fully netted position has zero settlement
fn is_fully_netted(buy_qty: Int, sell_qty: Int) -> Bool {
  buy_qty == sell_qty
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_equal_buys_sells_net_zero(
  qty via fuzz.int_between(1, 1000),
) {
  net_position(qty, qty) == 0 && is_fully_netted(qty, qty)
}

test prop_net_long_positive(
  vals via fuzz.both(fuzz.int_between(101, 1000), fuzz.int_between(1, 100)),
) {
  let (buy, sell) = vals
  net_position(buy, sell) > 0
}

test prop_settlement_zero_when_netted(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
) {
  let (qty, price) = vals
  settlement_amount(net_position(qty, qty), price) == 0
}

test prop_settlement_non_negative(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
) {
  let (net, price) = vals
  settlement_amount(net, price) >= 0
}
