use aiken/fuzz

/// Protocol fee collected on each fill (in bps)
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

// ── Property tests ───────────────────────────────────────────────────────────

test prop_zero_fee_bps_no_fee(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
) {
  let (qty, price) = vals
  fill_fee(qty, price, 0) == 0
}

test prop_seller_receives_less_than_gross(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 100)),
) {
  let (qty, fee_bps) = vals
  let price = 100
  seller_proceeds(qty, price, fee_bps) < qty * price
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
