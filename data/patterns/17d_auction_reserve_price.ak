use aiken/fuzz
use aiken/interval

/// Bid meets the reserve price
fn meets_reserve(bid: Int, reserve_price: Int) -> Bool {
  bid >= reserve_price
}

/// Auction can only settle if the winning bid meets the reserve
fn can_settle(
  validity_range: interval.Interval,
  end_time:       Int,
  winning_bid:    Int,
  reserve_price:  Int,
) -> Bool {
  interval.is_entirely_after(validity_range, end_time) && meets_reserve(winning_bid, reserve_price)
}

/// Auction can be cancelled (no sale) if bid never met reserve
fn can_cancel(
  validity_range: interval.Interval,
  end_time:       Int,
  winning_bid:    Int,
  reserve_price:  Int,
) -> Bool {
  interval.is_entirely_after(validity_range, end_time) && !meets_reserve(winning_bid, reserve_price)
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_bid_at_reserve_meets(
  reserve via fuzz.int_between(1, 10000),
) {
  meets_reserve(reserve, reserve)
}

test prop_bid_below_reserve_fails(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1001, 2000)),
) {
  let (bid, reserve) = vals
  !meets_reserve(bid, reserve)
}

test prop_settle_requires_reserve_met(
  reserve via fuzz.int_between(1, 1000),
) {
  can_settle(interval.after(1001), 1000, reserve, reserve)
}

test prop_cancel_when_reserve_not_met(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(501, 1000)),
) {
  let (bid, reserve) = vals
  can_cancel(interval.after(1001), 1000, bid, reserve)
}
