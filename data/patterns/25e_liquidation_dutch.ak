use aiken/fuzz
use cardano/transaction.{Transaction}

/// Dutch liquidation auction: collateral price starts high and drops over time
/// price = start_price - (start_price - floor_price) * elapsed / duration
fn dutch_liq_price(
  start_price: Int,
  floor_price: Int,
  elapsed:     Int,
  duration:    Int,
) -> Int {
  if elapsed >= duration {
    floor_price
  } else {
    let drop = (start_price - floor_price) * elapsed / duration
    start_price - drop
  }
}

/// Liquidator profit: collateral_value - price_paid - debt_repaid
fn liquidator_profit(
  collateral_value: Int,
  price_paid:       Int,
  debt_repaid:      Int,
) -> Int {
  collateral_value - price_paid - debt_repaid
}

pub type AuctionDatum {
  start_price: Int,
  floor_price: Int,
  duration: Int,
  auction_start_slot: Int,
  debt_repaid: Int,
  collateral_value: Int,
}

pub type AuctionRedeemer {
  elapsed: Int,
  price_paid: Int,
}

validator dutch_liquidation_auction {
  spend(
    datum: Option<AuctionDatum>,
    redeemer: AuctionRedeemer,
    _output_ref: Data,
    _self: Transaction,
  ) {
    expect Some(d) = datum
    let current_price =
      dutch_liq_price(d.start_price, d.floor_price, redeemer.elapsed, d.duration)
    let profit =
      liquidator_profit(d.collateral_value, redeemer.price_paid, d.debt_repaid)
    let price_acceptable = redeemer.price_paid >= current_price
    let elapsed_valid = redeemer.elapsed >= 0 && redeemer.elapsed <= d.duration
    let profitable = profit >= 0
    price_acceptable && elapsed_valid && profitable
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_price_starts_at_maximum(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(1, 99)),
) {
  let (start, floor) = vals
  dutch_liq_price(start, floor, 0, 100) == start
}

test prop_price_ends_at_floor(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(1, 99)),
) {
  let (start, floor) = vals
  dutch_liq_price(start, floor, 100, 100) == floor
}

test prop_price_non_increasing(
  vals via fuzz.both(fuzz.int_between(0, 99), fuzz.int_between(1, 99)),
) {
  let (t1, floor) = vals
  dutch_liq_price(100, floor, t1, 100) >= dutch_liq_price(100, floor, t1 + 1, 100)
}

test prop_profit_positive_at_floor(
  vals via fuzz.both(fuzz.int_between(200, 1000), fuzz.int_between(1, 50)),
) {
  let (collateral, debt) = vals
  // Buy at floor=1, repay debt=debt
  liquidator_profit(collateral, 1, debt) > 0
}