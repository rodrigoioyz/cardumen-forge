
use aiken/collection/list
use aiken/fuzz
use aiken/interval
use cardano/transaction.{OutputReference, Transaction}
pub type LoanDatum {
  borrower:       ByteArray,
  lender:         ByteArray,
  amount:         Int,
  early_deadline: Int,
  final_deadline: Int,
}

pub type LoanRedeemer {
  EarlyRepay
  Repay
  Reclaim
}

fn is_after_deadline(validity_range: interval.Interval, deadline: Int) -> Bool {
  interval.is_entirely_after(validity_range, deadline)
}

/// Early repay: before early_deadline (borrower gets a discount off-chain)
fn is_early_repay(validity_range: interval.Interval, early_deadline: Int) -> Bool {
  !is_after_deadline(validity_range, early_deadline)
}

validator loan_early_repay {
  spend(
    datum: Option<LoanDatum>,
    redeemer: LoanRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      EarlyRepay ->
        is_early_repay(self.validity_range, d.early_deadline) && list.has(
          self.extra_signatories,
          d.borrower,
        )
      Repay ->
        !is_after_deadline(self.validity_range, d.final_deadline) && list.has(
          self.extra_signatories,
          d.borrower,
        )
      Reclaim ->
        is_after_deadline(self.validity_range, d.final_deadline) && list.has(
          self.extra_signatories,
          d.lender,
        )
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_early_repay_before_early_deadline(
  deadline via fuzz.int_between(500, 999),
) {
  is_early_repay(interval.before(deadline), deadline)
}

test prop_early_repay_after_early_deadline_false(
  deadline via fuzz.int_between(0, 500),
) {
  !is_early_repay(interval.after(deadline + 1), deadline)
}

test prop_after_final_is_reclaim(
  deadline via fuzz.int_between(0, 999),
) {
  is_after_deadline(interval.after(1000), deadline)
}

test prop_before_final_not_reclaim(
  deadline via fuzz.int_between(1001, 2000),
) {
  !is_after_deadline(interval.before(1000), deadline)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// is_early_repay returns False when the validity range is entirely after the
/// early deadline, so `expect` must fail for every input in this range.
test prop_early_repay_rejected_when_past_deadline(
  deadline via fuzz.int_between(0, 999),
) fail {
  // interval.after(deadline + 1) is entirely after `deadline`
  expect is_early_repay(interval.after(deadline + 1), deadline)
}

/// is_after_deadline returns False when the validity range ends strictly
/// before the deadline, so reclaim must always be rejected here.
test prop_not_after_deadline_when_range_before(
  deadline via fuzz.int_between(1001, 2000),
) fail {
  // interval.before(1000) ends at 1000, which is before every deadline in [1001,2000]
  expect is_after_deadline(interval.before(1000), deadline)
}

/// is_early_repay is False for an interval that is entirely after a deadline of 0,
/// confirming the boundary: even a deadline of 0 is violated by after(1).
test prop_early_repay_rejected_at_zero_deadline() fail {
  expect is_early_repay(interval.after(1), 0)
}

/// is_after_deadline returns False when the range is entirely before the
/// deadline, proven here with a large deadline so the range can never exceed it.
test prop_is_after_deadline_false_for_small_range(
  deadline via fuzz.int_between(5000, 10000),
) fail {
  // interval.before(100) ends at 100, well before any deadline in [5000,10000]
  expect is_after_deadline(interval.before(100), deadline)
}