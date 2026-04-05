
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A validity range that starts strictly after the deadline must make
/// is_on_time return False.  Using interval.after(dl+1) guarantees the
/// entire interval lies past the deadline, so is_after_deadline returns True
/// and is_on_time returns False.
test prop_late_installment_rejected(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(1, 100)),
) fail {
  let (base, slots) = vals
  let dl = installment_deadline(base, 1, slots)
  expect is_on_time(interval.after(dl + 1), base, 1, slots)
}

/// Installment 2 is always later than installment 1, so a validity range
/// that is already past installment-1's deadline but at the installment-2
/// boundary is still past installment 1 — confirm is_on_time is False for
/// installment 1 when the range is entirely after it.
test prop_late_first_installment_always_rejected(
  vals via fuzz.both(fuzz.int_between(1, 300), fuzz.int_between(10, 50)),
) fail {
  let (base, slots) = vals
  // deadline for installment 1
  let dl1 = installment_deadline(base, 1, slots)
  // shift the range well past deadline 1
  expect is_on_time(interval.after(dl1 + slots + 1), base, 1, slots)
}

/// is_after_deadline should return False when the interval ends strictly
/// before the deadline — but here we force it to return True by placing the
/// interval entirely after the deadline, then `expect` that result directly,
/// which trivially verifies the helper returns True; to get a *fail* test we
/// instead assert the negation via is_on_time wrapping, confirming the
/// payment-on-time check rejects a very-late range for installment 3.
test prop_installment3_late_rejected(
  vals via fuzz.both(fuzz.int_between(0, 200), fuzz.int_between(5, 30)),
) fail {
  let (base, slots) = vals
  let dl3 = installment_deadline(base, 3, slots)
  // interval entirely after installment-3 deadline → is_on_time must be False
  expect is_on_time(interval.after(dl3 + 1), base, 3, slots)
}

/// Zero-th installment has deadline == base.  A validity range that starts
/// after base must make is_on_time False for installment 0.
test prop_installment0_past_base_rejected(
  vals via fuzz.both(fuzz.int_between(0, 1000), fuzz.int_between(1, 100)),
) fail {
  let (base, slots) = vals
  // deadline for installment 0 is exactly base
  // interval.after(base + 1) is entirely past that deadline
  expect is_on_time(interval.after(base + 1), base, 0, slots)
}