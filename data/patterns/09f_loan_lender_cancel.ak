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
