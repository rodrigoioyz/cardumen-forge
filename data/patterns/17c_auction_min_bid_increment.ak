
/// New bid must exceed previous by at least min_increment
use aiken/fuzz
use aiken/interval
use cardano/transaction.{Transaction}
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
  bid_end: Int,
  new_bid: Int,
  prev_bid: Int,
  min_increment: Int,
) -> Bool {
  in_bidding_window(validity_range, bid_end) && valid_bid(new_bid, prev_bid, min_increment)
}

pub type AuctionDatum {
  bid_end: Int,
  prev_bid: Int,
  min_increment: Int,
}

pub type AuctionRedeemer {
  new_bid: Int,
}

validator auction_min_bid_increment {
  spend(
    datum: Option<AuctionDatum>,
    redeemer: AuctionRedeemer,
    _output_reference: Data,
    self: Transaction,
  ) {
    when datum is {
      None -> False
      Some(d) ->
        bid_accepted(
          self.validity_range,
          d.bid_end,
          redeemer.new_bid,
          d.prev_bid,
          d.min_increment,
        )
    }
  }

  else(_) {
    fail
  }
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

// ── Negative / fail tests ─────────────────────────────────────────────────────

/// A bid strictly below the required increment must always be rejected.
/// new_bid = prev_bid + increment - 1 is always one lovelace short.
test prop_insufficient_bid_always_fails(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(2, 500)),
) fail {
  let (prev_bid, increment) = vals
  // new_bid is exactly one less than required → valid_bid must return False
  expect valid_bid(prev_bid + increment - 1, prev_bid, increment)
}

/// A bid equal to prev_bid (increment = 0 is excluded; we use increment >= 1)
/// where new_bid == prev_bid is always strictly below prev_bid + increment.
test prop_same_bid_as_prev_fails(
  vals via fuzz.both(fuzz.int_between(1, 2000), fuzz.int_between(1, 500)),
) fail {
  let (prev_bid, increment) = vals
  // new_bid == prev_bid < prev_bid + increment → always False
  expect valid_bid(prev_bid, prev_bid, increment)
}

/// Bidding after the window has closed must always be rejected.
/// interval.after(1000) is entirely after bid_end values 0..999.
test prop_bid_outside_window_always_fails(
  bid_end via fuzz.int_between(0, 999),
) fail {
  // validity_range starts at 1000, bid_end <= 999 → window already closed
  expect in_bidding_window(interval.after(1000), bid_end)
}

/// Combined check fails when the bid is insufficient even inside the window.
/// The window is valid (bid_end > 2000), but new_bid < prev_bid + increment.
test prop_combined_fails_on_bad_increment(
  vals via fuzz.both(fuzz.int_between(2001, 5000), fuzz.int_between(2, 500)),
) fail {
  let (bid_end, increment) = vals
  // prev_bid = 1000, new_bid = 1000 + increment - 1 → one short
  expect bid_accepted(interval.before(1000), bid_end, 1000 + increment - 1, 1000, increment)
}