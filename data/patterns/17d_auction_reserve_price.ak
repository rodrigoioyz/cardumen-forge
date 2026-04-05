
/// Bid meets the reserve price
use aiken/fuzz
use aiken/interval
use cardano/transaction.{Transaction}
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

// ── Validator ────────────────────────────────────────────────────────────────

pub type AuctionDatum {
  end_time: Int,
  reserve_price: Int,
  winning_bid: Int,
}

pub type AuctionRedeemer {
  Settle
  Cancel
}

validator auction_reserve_price {
  spend(
    datum: Option<AuctionDatum>,
    redeemer: AuctionRedeemer,
    _output_reference: Data,
    self: Transaction,
  ) {
    expect Some(d) = datum
    when redeemer is {
      Settle ->
        can_settle(self.validity_range, d.end_time, d.winning_bid, d.reserve_price)
      Cancel ->
        can_cancel(self.validity_range, d.end_time, d.winning_bid, d.reserve_price)
    }
  }

  else(_) {
    fail
  }
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// bid strictly below reserve must never meet reserve
test prop_bid_strictly_below_reserve_rejected(
  vals via fuzz.both(fuzz.int_between(1, 999), fuzz.int_between(1000, 2000)),
) fail {
  let (bid, reserve) = vals
  expect meets_reserve(bid, reserve)
}

/// meets_reserve with zero bid against positive reserve must fail
test prop_zero_bid_below_positive_reserve_rejected(
  reserve via fuzz.int_between(1, 10000),
) fail {
  expect meets_reserve(0, reserve)
}

/// can_settle must fail when bid is below reserve (even after end_time)
test prop_settle_below_reserve_rejected(
  vals via fuzz.both(fuzz.int_between(1, 499), fuzz.int_between(500, 1000)),
) fail {
  let (bid, reserve) = vals
  // validity_range is entirely after end_time=999, but bid < reserve
  expect can_settle(interval.after(1000), 999, bid, reserve)
}

/// can_cancel must fail when bid meets or exceeds reserve (no cancellation allowed)
test prop_cancel_when_reserve_met_rejected(
  vals via fuzz.both(fuzz.int_between(500, 1000), fuzz.int_between(1, 500)),
) fail {
  let (bid, reserve) = vals
  // bid >= reserve means meets_reserve is True, so can_cancel must be False
  expect can_cancel(interval.after(1001), 1000, bid, reserve)
}