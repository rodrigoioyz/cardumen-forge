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
