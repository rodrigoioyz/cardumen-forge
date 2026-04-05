
/// Net position after matching N buy orders against M sell orders
/// Simplified: single buyer/seller, net_qty = buy_qty - sell_qty
use aiken/fuzz
use cardano/transaction.{Transaction}
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

// ── Datum / Redeemer ─────────────────────────────────────────────────────────

pub type OrderDatum {
  buy_qty: Int,
  sell_qty: Int,
  clearing_price: Int,
  min_settlement: Int,
}

pub type OrderRedeemer {
  Settle
  Cancel
}

// ── Validator ────────────────────────────────────────────────────────────────

validator order_netting {
  spend(
    datum: Option<OrderDatum>,
    redeemer: OrderRedeemer,
    _own_ref: Data,
    _self: Transaction,
  ) {
    expect Some(d) = datum
    when redeemer is {
      Cancel -> True
      Settle -> {
        let net = net_position(d.buy_qty, d.sell_qty)
        let amount = settlement_amount(net, d.clearing_price)
        if is_fully_netted(d.buy_qty, d.sell_qty) {
          amount == 0
        } else {
          amount >= d.min_settlement
        }
      }
    }
  }

  else(_ctx) {
    fail
  }
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// buy_qty != sell_qty means is_fully_netted must return False.
/// buy is strictly greater than sell so they can never be equal.
test prop_unequal_quantities_not_netted(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(101, 200)),
) fail {
  let (sell, buy) = vals
  expect is_fully_netted(buy, sell)
}

/// sell_qty strictly greater than buy_qty — also never fully netted.
test prop_net_short_not_netted(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(501, 1000)),
) fail {
  let (buy, sell) = vals
  expect is_fully_netted(buy, sell)
}

/// settlement_amount of a strictly positive net with a strictly positive price
/// can never be zero, so asserting it equals zero must always fail.
test prop_nonzero_net_settlement_not_zero(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
) fail {
  let (net, price) = vals
  expect settlement_amount(net, price) == 0
}

/// A long position (buy > sell) is never fully netted.
/// Using a unit test with hardcoded values to be maximally explicit.
test unit_long_position_not_fully_netted() fail {
  expect is_fully_netted(10, 5)
}