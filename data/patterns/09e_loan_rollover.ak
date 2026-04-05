use aiken/collection/list
use aiken/fuzz
use aiken/interval
use cardano/transaction.{OutputReference, Transaction}

pub type LoanDatum {
  lender:          ByteArray,
  borrower:        ByteArray,
  amount:          Int,
  deadline:        Int,
  rollover_slots:  Int,
  rollovers_used:  Int,
  max_rollovers:   Int,
}

pub type LoanRedeemer {
  Repay
  Rollover
  Reclaim
}

fn is_after_deadline(validity_range: interval.Interval, deadline: Int) -> Bool {
  interval.is_entirely_after(validity_range, deadline)
}

/// Extended deadline after using a rollover
fn rolled_deadline(deadline: Int, rollover_slots: Int) -> Int {
  deadline + rollover_slots
}

/// Rollover allowed only before deadline and within max_rollovers
fn can_rollover(
  validity_range:  interval.Interval,
  deadline:        Int,
  rollovers_used:  Int,
  max_rollovers:   Int,
) -> Bool {
  !is_after_deadline(validity_range, deadline) && rollovers_used < max_rollovers
}

validator loan_rollover {
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
      Rollover ->
        can_rollover(
          self.validity_range,
          d.deadline,
          d.rollovers_used,
          d.max_rollovers,
        ) && list.has(self.extra_signatories, d.borrower)
      Reclaim ->
        is_after_deadline(self.validity_range, d.deadline) && list.has(
          self.extra_signatories,
          d.lender,
        )
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_rolled_deadline_grows(
  vals via fuzz.both(fuzz.int_between(0, 1000), fuzz.int_between(1, 500)),
) {
  let (deadline, slots) = vals
  rolled_deadline(deadline, slots) > deadline
}

test prop_can_rollover_before_deadline_under_max(
  vals via fuzz.both(fuzz.int_between(1001, 2000), fuzz.int_between(0, 4)),
) {
  let (deadline, used) = vals
  can_rollover(interval.before(deadline), deadline, used, 5)
}

test prop_cannot_rollover_after_deadline(
  deadline via fuzz.int_between(0, 999),
) {
  !can_rollover(interval.after(deadline + 1), deadline, 0, 5)
}

test prop_cannot_rollover_max_reached(
  vals via fuzz.both(fuzz.int_between(1001, 2000), fuzz.int_between(0, 4)),
) {
  let (deadline, max) = vals
  !can_rollover(interval.before(deadline), deadline, max, max)
}
