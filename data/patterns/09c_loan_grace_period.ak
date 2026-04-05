
use aiken/collection/list
use aiken/fuzz
use aiken/interval
use cardano/transaction.{OutputReference, Transaction}
pub type LoanDatum {
  lender:       ByteArray,
  borrower:     ByteArray,
  amount:       Int,
  deadline:     Int,
  grace_period: Int,
}

pub type LoanRedeemer {
  Repay
  Reclaim
}

fn is_after_deadline(validity_range: interval.Interval, deadline: Int) -> Bool {
  interval.is_entirely_after(validity_range, deadline)
}

/// Lender may reclaim only after deadline + grace_period
fn is_after_grace_period(
  validity_range: interval.Interval,
  deadline:       Int,
  grace:          Int,
) -> Bool {
  interval.is_entirely_after(validity_range, deadline + grace)
}

validator loan_grace_period {
  spend(
    datum: Option<LoanDatum>,
    redeemer: LoanRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      Repay ->
        !is_after_deadline(self.validity_range, d.deadline) && list.has(
          self.extra_signatories,
          d.borrower,
        )
      Reclaim ->
        is_after_grace_period(
          self.validity_range,
          d.deadline,
          d.grace_period,
        ) && list.has(self.extra_signatories, d.lender)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_grace_period_after_deadline_plus_grace(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(1, 100)),
) {
  let (deadline, grace) = vals
  is_after_grace_period(interval.after(deadline + grace + 1), deadline, grace)
}

test prop_grace_period_at_deadline_only_false(
  vals via fuzz.both(fuzz.int_between(100, 500), fuzz.int_between(10, 50)),
) {
  let (deadline, grace) = vals
  !is_after_grace_period(interval.before(deadline + grace), deadline, grace)
}

test prop_grace_deadline_arithmetic(
  vals via fuzz.both(fuzz.int_between(0, 1000), fuzz.int_between(0, 1000)),
) {
  let (deadline, grace) = vals
  deadline + grace >= deadline
}

test prop_repay_before_deadline(deadline via fuzz.int_between(1001, 2000)) {
  !is_after_deadline(interval.before(1000), deadline)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// is_after_grace_period must fail when the validity range ends BEFORE the
/// grace period boundary. interval.before(n) is entirely before n, so
/// is_entirely_after returns False for any deadline+grace >= n.
test prop_grace_period_not_reached_fails(
  vals via fuzz.both(fuzz.int_between(50, 200), fuzz.int_between(1, 50)),
) fail {
  let (deadline, grace) = vals
  // validity range ends at deadline+grace-1, so it is NOT after deadline+grace
  expect is_after_grace_period(
    interval.before(deadline + grace - 1),
    deadline,
    grace,
  )
}

/// is_after_deadline must fail when the validity range is entirely BEFORE the
/// deadline, meaning the tx fires too early.
test prop_is_after_deadline_too_early_fails(
  deadline via fuzz.int_between(100, 1000),
) fail {
  // interval.before(deadline) ends strictly before deadline → not after it
  expect is_after_deadline(interval.before(deadline), deadline)
}

/// is_after_grace_period must fail when grace is zero and the range ends
/// exactly at the deadline (before(deadline) is not after deadline+0).
test prop_zero_grace_at_deadline_fails(
  deadline via fuzz.int_between(1, 500),
) fail {
  expect is_after_grace_period(interval.before(deadline), deadline, 0)
}

/// is_after_deadline must fail when the validity range ends well before the
/// deadline (range upper bound << deadline).
test prop_is_after_deadline_far_too_early_fails(
  vals via fuzz.both(fuzz.int_between(1, 50), fuzz.int_between(100, 500)),
) fail {
  let (range_end, extra) = vals
  // deadline is far beyond the range end
  expect is_after_deadline(interval.before(range_end), range_end + extra)
}