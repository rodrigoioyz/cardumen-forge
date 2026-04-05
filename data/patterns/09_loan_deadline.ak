
use aiken/collection/list
use aiken/fuzz
use aiken/interval
use cardano/transaction.{OutputReference, Transaction}
pub type LoanDatum {
  lender:   ByteArray,
  borrower: ByteArray,
  amount:   Int,
  deadline: Int,
}

pub type LoanRedeemer {
  Repay
  Reclaim
}

/// True when the tx validity range is entirely after the deadline
fn is_after_deadline(
  validity_range: interval.Interval,
  deadline:       Int,
) -> Bool {
  interval.is_entirely_after(validity_range, deadline)
}

validator loan_deadline {
  spend(
    datum: Option<LoanDatum>,
    redeemer: LoanRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      Repay ->
        // Borrower repays before deadline — they must sign
        !is_after_deadline(self.validity_range, d.deadline)
          && list.has(self.extra_signatories, d.borrower)
      Reclaim ->
        // Lender reclaims collateral only after deadline passes
        is_after_deadline(self.validity_range, d.deadline)
          && list.has(self.extra_signatories, d.lender)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_is_after_deadline_entirely_after(
  deadline via fuzz.int_between(0, 999),
) {
  // interval.after(1000) → lower bound = 1000, no upper bound
  is_after_deadline(interval.after(1000), deadline)
}

test prop_is_after_deadline_entirely_before(
  deadline via fuzz.int_between(1001, 2000),
) {
  // interval entirely before deadline → not after
  !is_after_deadline(interval.before(1000), deadline)
}

test prop_repay_reclaim_mutually_exclusive(
  deadline via fuzz.int_between(1, 1000),
) {
  let range_after  = interval.after(deadline + 1)
  let range_before = interval.before(deadline)
  let after_flag  = is_after_deadline(range_after, deadline)
  let before_flag = is_after_deadline(range_before, deadline)
  after_flag && !before_flag
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A range that ends strictly before the deadline is NOT entirely after it.
/// interval.before(500) ends at 500; deadline >= 500 means the range cannot
/// be entirely after the deadline, so is_after_deadline returns False.
test prop_before_range_not_after_deadline(
  deadline via fuzz.int_between(500, 2000),
) fail {
  expect is_after_deadline(interval.before(500), deadline)
}

/// interval.between(lo, hi) where hi <= deadline means the range ends before
/// or at the deadline — definitely not entirely after it.
test prop_range_ending_at_deadline_not_after(
  deadline via fuzz.int_between(100, 1000),
) fail {
  // The range [0, deadline] cannot be entirely after `deadline`
  expect is_after_deadline(interval.between(0, deadline), deadline)
}

/// A range starting well before the deadline and ending at a fixed point (50)
/// is never entirely after a deadline of 1 or more.
test prop_early_range_never_after_positive_deadline(
  deadline via fuzz.int_between(1, 500),
) fail {
  // interval.between(0, 50): the range starts at 0, which is <= any deadline >= 1
  expect is_after_deadline(interval.between(0, 50), deadline)
}

/// The "everything" interval is never entirely after any finite deadline
/// because it includes values at or before the deadline.
test prop_everything_interval_not_after_deadline() fail {
  // interval.everything covers all integers; not entirely after any deadline
  expect is_after_deadline(interval.everything, 0)
}