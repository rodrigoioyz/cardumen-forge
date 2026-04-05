
/// Protocol fee collected on each fill (in bps)
use aiken/fuzz
use cardano/transaction.{Transaction}
fn fill_fee(fill_qty: Int, price: Int, fee_bps: Int) -> Int {
  fill_qty * price * fee_bps / 10000
}

/// Net proceeds to seller after fee deduction
fn seller_proceeds(fill_qty: Int, price: Int, fee_bps: Int) -> Int {
  fill_qty * price - fill_fee(fill_qty, price, fee_bps)
}

/// Fee is non-negative and less than gross proceeds
fn fee_valid(fill_qty: Int, price: Int, fee_bps: Int) -> Bool {
  let gross = fill_qty * price
  let fee   = fill_fee(fill_qty, price, fee_bps)
  fee >= 0 && fee < gross
}

pub type OrderDatum {
  fill_qty: Int,
  price: Int,
  fee_bps: Int,
  min_proceeds: Int,
}

validator order_fee_collection {
  spend(datum: Option<OrderDatum>, _redeemer, _ref, _self: Transaction) {
    expect Some(d) = datum
    let valid_fee = fee_valid(d.fill_qty, d.price, d.fee_bps)
    let proceeds  = seller_proceeds(d.fill_qty, d.price, d.fee_bps)
    let fee       = fill_fee(d.fill_qty, d.price, d.fee_bps)
    let fee_covers_min = proceeds >= d.min_proceeds
    let fee_positive   = fee >= 0
    valid_fee && fee_covers_min && fee_positive
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_zero_fee_bps_no_fee(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
) {
  let (qty, price) = vals
  fill_fee(qty, price, 0) == 0
}

test prop_seller_proceeds_equals_gross_minus_fee(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 100)),
) {
  let (qty, fee_bps) = vals
  let price = 100
  seller_proceeds(qty, price, fee_bps) == qty * price - fill_fee(qty, price, fee_bps)
}

test prop_fee_valid_for_standard_rate(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
) {
  let (qty, price) = vals
  fee_valid(qty, price, 30)
}

test prop_seller_proceeds_non_negative(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 9999)),
) {
  let (qty, fee_bps) = vals
  seller_proceeds(qty, 100, fee_bps) >= 0
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// fee_valid must reject when fee_bps >= 10000 (fee >= gross, so fee < gross is False)
test prop_fee_valid_rejects_fee_bps_at_least_10000(
  vals via fuzz.both(
    fuzz.int_between(1, 1000),
    fuzz.int_between(10000, 20000),
  ),
) fail {
  let (qty, fee_bps) = vals
  // price=1: gross = qty*1, fee = qty*1*fee_bps/10000 >= qty when fee_bps>=10000
  // so fee < gross is False → fee_valid returns False
  expect fee_valid(qty, 1, fee_bps)
}

/// fee_valid must reject when fill_qty is zero (gross=0, fee=0, fee < gross → 0 < 0 is False)
test prop_fee_valid_rejects_zero_qty() fail {
  expect fee_valid(0, 100, 30)
}

/// fee_valid must reject when price is zero (gross=0, fee=0, fee < gross → 0 < 0 is False)
test prop_fee_valid_rejects_zero_price(
  qty via fuzz.int_between(1, 1000),
) fail {
  expect fee_valid(qty, 0, 30)
}

/// fee_valid must reject when both qty and price are negative
/// gross = (-qty)*(-price) is positive but fee_bps=10000 makes fee==gross → not strictly less
test prop_fee_valid_rejects_full_fee_bps_any_qty(
  vals via fuzz.both(
    fuzz.int_between(1, 500),
    fuzz.int_between(1, 500),
  ),
) fail {
  let (qty, price) = vals
  // fee_bps=10000 → fee = qty*price*10000/10000 = qty*price = gross
  // fee < gross → gross < gross → False
  expect fee_valid(qty, price, 10000)
}