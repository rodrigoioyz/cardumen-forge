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
