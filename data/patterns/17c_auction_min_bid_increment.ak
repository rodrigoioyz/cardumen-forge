use aiken/fuzz
use aiken/interval

/// New bid must exceed previous by at least min_increment
fn valid_bid(new_bid: Int, prev_bid: Int, min_increment: Int) -> Bool {
  new_bid >= prev_bid + min_increment
}

/// Bid is within the bidding window
fn in_bidding_window(validity_range: interval.Interval, bid_end: Int) -> Bool {
  !interval.is_entirely_after(validity_range, bid_end)
}

/// Combined check: valid time window AND sufficient increment
fn bid_accepted(
  validity_range: interval.Interval,
  bid_end:        Int,
  new_bid:        Int,
  prev_bid:       Int,
  min_increment:  Int,
) -> Bool {
  in_bidding_window(validity_range, bid_end) && valid_bid(new_bid, prev_bid, min_increment)
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_exact_increment_accepted(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 100)),
) {
  let (prev_bid, increment) = vals
  valid_bid(prev_bid + increment, prev_bid, increment)
}

test prop_below_increment_rejected(
  vals via fuzz.both(fuzz.int_between(2, 1000), fuzz.int_between(2, 100)),
) {
  let (prev_bid, increment) = vals
  !valid_bid(prev_bid + increment - 1, prev_bid, increment)
}

test prop_bid_accepted_inside_window(
  vals via fuzz.both(fuzz.int_between(1001, 2000), fuzz.int_between(1, 100)),
) {
  let (bid_end, increment) = vals
  bid_accepted(interval.before(1000), bid_end, 200, 100, increment)
}

test prop_bid_rejected_outside_window(
  vals via fuzz.both(fuzz.int_between(0, 999), fuzz.int_between(1, 100)),
) {
  let (bid_end, increment) = vals
  !bid_accepted(interval.after(1000), bid_end, 200, 100, increment)
}
