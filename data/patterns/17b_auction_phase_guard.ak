use aiken/fuzz
use aiken/interval

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
