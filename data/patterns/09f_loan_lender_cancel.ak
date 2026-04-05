
use aiken/collection/list
use aiken/fuzz
use aiken/interval
use cardano/transaction.{OutputReference, Transaction}
pub type LoanDatum {
  lender:     ByteArray,
  borrower:   ByteArray,
  amount:     Int,
  start_date: Int,
  deadline:   Int,
}

pub type LoanRedeemer {
  Cancel
  Repay
  Reclaim
}

fn is_after_deadline(validity_range: interval.Interval, deadline: Int) -> Bool {
  interval.is_entirely_after(validity_range, deadline)
}

/// Lender can cancel only before the loan start date (pre-activation)
fn is_before_start(validity_range: interval.Interval, start_date: Int) -> Bool {
  !is_after_deadline(validity_range, start_date)
}

validator loan_lender_cancel {
  spend(
    datum: Option<LoanDatum>,
    redeemer: LoanRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      Cancel ->
        is_before_start(self.validity_range, d.start_date) && list.has(
          self.extra_signatories,
          d.lender,
        )
      Repay ->
        !is_after_deadline(self.validity_range, d.deadline) && list.has(
          self.extra_signatories,
          d.borrower,
        )
      Reclaim ->
        is_after_deadline(self.validity_range, d.deadline) && list.has(
          self.extra_signatories,
          d.lender,
        )
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_cancel_before_start(start via fuzz.int_between(1001, 2000)) {
  is_before_start(interval.before(1000), start)
}

test prop_cancel_after_start_false(start via fuzz.int_between(0, 999)) {
  !is_before_start(interval.after(1000), start)
}

test prop_reclaim_after_deadline(deadline via fuzz.int_between(0, 999)) {
  is_after_deadline(interval.after(1000), deadline)
}

test prop_repay_reclaim_exclusive(deadline via fuzz.int_between(1, 1000)) {
  let after  = is_after_deadline(interval.after(deadline + 1), deadline)
  let before = is_after_deadline(interval.before(deadline), deadline)
  after && !before
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// is_before_start returns False when the validity range is entirely after
/// the start_date, i.e. the lender is trying to cancel after the loan started.
test prop_cancel_after_start_rejected(
  start via fuzz.int_between(0, 999),
) fail {
  // interval.after(1000) means the tx is valid only after slot 1000,
  // and start <= 999, so the range is entirely after start → is_before_start = False
  expect is_before_start(interval.after(1000), start)
}

/// is_after_deadline returns False when the validity range ends strictly
/// before the deadline, so a Reclaim attempt would be correctly rejected.
test prop_reclaim_before_deadline_rejected(
  deadline via fuzz.int_between(1001, 3000),
) fail {
  // interval.before(1000) means the tx is valid only before slot 1000,
  // deadline >= 1001, so the range is NOT entirely after the deadline → False
  expect is_after_deadline(interval.before(1000), deadline)
}

/// is_after_deadline returns False for a range that ends at exactly the
/// deadline (boundary: the interval must be STRICTLY after, not touching).
test prop_reclaim_at_deadline_boundary_rejected() fail {
  // deadline = 500; interval.before(500) ends at 500, not strictly after
  expect is_after_deadline(interval.before(500), 500)
}

/// is_before_start returns False when validity_range is entirely after
/// a start_date of 0 (edge-case: earliest possible start).
test prop_cancel_zero_start_after_range_rejected(
  slot via fuzz.int_between(1, 500),
) fail {
  // interval.after(slot) is entirely after slot, which is > 0 = start_date,
  // so is_after_deadline(range, 0) = True → is_before_start = False
  expect is_before_start(interval.after(slot), 0)
}