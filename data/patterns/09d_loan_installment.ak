use aiken/collection/list
use aiken/fuzz
use aiken/interval
use cardano/transaction.{OutputReference, Transaction}

pub type LoanDatum {
  borrower:        ByteArray,
  lender:          ByteArray,
  amount:          Int,
  base_deadline:   Int,
  interval_slots:  Int,
}

pub type LoanRedeemer {
  PayInstallment { installment_num: Int }
  Reclaim
}

fn is_after_deadline(validity_range: interval.Interval, deadline: Int) -> Bool {
  interval.is_entirely_after(validity_range, deadline)
}

/// Deadline for installment N: base + N * interval_slots
fn installment_deadline(base: Int, num: Int, interval_slots: Int) -> Int {
  base + num * interval_slots
}

/// Installment N must be paid before its deadline
fn is_on_time(
  validity_range: interval.Interval,
  base:           Int,
  num:            Int,
  interval_slots: Int,
) -> Bool {
  !is_after_deadline(
    validity_range,
    installment_deadline(base, num, interval_slots),
  )
}

validator loan_installment {
  spend(
    datum: Option<LoanDatum>,
    redeemer: LoanRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      PayInstallment { installment_num } ->
        is_on_time(
          self.validity_range,
          d.base_deadline,
          installment_num,
          d.interval_slots,
        ) && list.has(self.extra_signatories, d.borrower)
      Reclaim -> {
        let final = installment_deadline(d.base_deadline, 3, d.interval_slots)
        is_after_deadline(self.validity_range, final) && list.has(
          self.extra_signatories,
          d.lender,
        )
      }
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_installment_deadline_zero(
  vals via fuzz.both(fuzz.int_between(0, 1000), fuzz.int_between(1, 100)),
) {
  let (base, slots) = vals
  installment_deadline(base, 0, slots) == base
}

test prop_installment_deadline_grows(
  vals via fuzz.both(fuzz.int_between(0, 1000), fuzz.int_between(1, 100)),
) {
  let (base, slots) = vals
  installment_deadline(base, 2, slots) > installment_deadline(base, 1, slots)
}

test prop_on_time_before_deadline(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(1, 100)),
) {
  let (base, slots) = vals
  let dl = installment_deadline(base, 1, slots)
  is_on_time(interval.before(dl), base, 1, slots)
}

test prop_late_installment_fails(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(1, 100)),
) {
  let (base, slots) = vals
  let dl = installment_deadline(base, 1, slots)
  !is_on_time(interval.after(dl + 1), base, 1, slots)
}
