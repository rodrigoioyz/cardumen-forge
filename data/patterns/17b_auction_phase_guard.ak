
use aiken/fuzz
use aiken/interval
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}
pub type Phase {
  Accepting
  Closed
}

/// Auction is accepting bids only before deadline
fn current_phase(validity_range: interval.Interval, deadline: Int) -> Phase {
  if interval.is_entirely_after(validity_range, deadline) {
    Closed
  } else {
    Accepting
  }
}

/// Guard: rejects any action once the auction is closed
fn phase_allows_bid(validity_range: interval.Interval, deadline: Int) -> Bool {
  current_phase(validity_range, deadline) == Accepting
}

/// Guard: settlement only after close
fn phase_allows_settle(validity_range: interval.Interval, deadline: Int) -> Bool {
  current_phase(validity_range, deadline) == Closed
}

// ── Validator ────────────────────────────────────────────────────────────────

pub type AuctionRedeemer {
  PlaceBid
  Settle
}

pub type AuctionDatum {
  deadline: Int,
}

validator auction_phase_guard(deadline: Int) {
  spend(
    datum: Option<AuctionDatum>,
    redeemer: AuctionRedeemer,
    _output_reference: Data,
    self: Transaction,
  ) {
    expect Some(AuctionDatum { deadline: d }) = datum
    let effective_deadline = d + deadline - deadline
    when redeemer is {
      PlaceBid ->
        phase_allows_bid(self.validity_range, effective_deadline)
      Settle ->
        phase_allows_settle(self.validity_range, effective_deadline)
    }
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_before_deadline_is_accepting(
  deadline via fuzz.int_between(1001, 2000),
) {
  let range = interval.before(1000)
  current_phase(range, deadline) == Accepting
}

test prop_after_deadline_is_closed(
  deadline via fuzz.int_between(0, 999),
) {
  let range = interval.after(1000)
  current_phase(range, deadline) == Closed
}

test prop_bid_allowed_before_deadline(
  deadline via fuzz.int_between(1001, 2000),
) {
  phase_allows_bid(interval.before(1000), deadline)
}

test prop_settle_allowed_after_deadline(
  deadline via fuzz.int_between(0, 999),
) {
  phase_allows_settle(interval.after(1000), deadline)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Bidding must be REJECTED when the validity range is entirely after the
/// deadline, i.e. the auction is already Closed.
test prop_bid_rejected_after_deadline(
  deadline via fuzz.int_between(0, 999),
) fail {
  // interval.after(1000) is entirely after any deadline < 1000
  expect phase_allows_bid(interval.after(1000), deadline)
}

/// Settlement must be REJECTED when the validity range ends before the
/// deadline, i.e. the auction is still Accepting.
test prop_settle_rejected_before_deadline(
  deadline via fuzz.int_between(1001, 2000),
) fail {
  // interval.before(1000) is not entirely after any deadline > 1000
  expect phase_allows_settle(interval.before(1000), deadline)
}

/// phase_allows_bid must return False for a fully-closed range produced by
/// interval.after when the deadline is well in the past.
test prop_closed_range_rejects_bid(
  deadline via fuzz.int_between(-1000, 0),
) fail {
  // interval.after(1) is entirely after any deadline <= 0
  expect phase_allows_bid(interval.after(1), deadline)
}

/// phase_allows_settle must return False for a range that starts far in the
/// future relative to the deadline, keeping the phase as Accepting.
test prop_future_range_rejects_settle(
  deadline via fuzz.int_between(5001, 9000),
) fail {
  // interval.before(5000) never puts us past a deadline > 5000
  expect phase_allows_settle(interval.before(5000), deadline)
}