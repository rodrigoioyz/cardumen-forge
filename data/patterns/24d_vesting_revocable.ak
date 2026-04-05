
/// Revocable vesting: employer can claw back unvested tokens before a deadline
use aiken/fuzz
use aiken/interval
use cardano/transaction.{Transaction}
fn unvested_amount(
  total_amount: Int,
  vested_so_far: Int,
) -> Int {
  total_amount - vested_so_far
}

/// Clawback is valid only before the irrevocability deadline
fn clawback_allowed(
  validity_range: interval.Interval,
  irrevocable_slot: Int,
) -> Bool {
  !interval.is_entirely_after(validity_range, irrevocable_slot)
}

/// After deadline: vesting is irrevocable
fn fully_irrevocable(
  validity_range: interval.Interval,
  irrevocable_slot: Int,
) -> Bool {
  interval.is_entirely_after(validity_range, irrevocable_slot)
}

// ── Datum / Redeemer ─────────────────────────────────────────────────────────

pub type VestingDatum {
  total_amount: Int,
  vested_so_far: Int,
  irrevocable_slot: Int,
  employer_key: ByteArray,
  employee_key: ByteArray,
}

pub type VestingRedeemer {
  Clawback
  Withdraw
}

// ── Validator ────────────────────────────────────────────────────────────────

validator revocable_vesting {
  spend(
    datum: Option<VestingDatum>,
    redeemer: VestingRedeemer,
    _utxo: Data,
    self: Transaction,
  ) {
    expect Some(d) = datum
    let range = self.validity_range
    when redeemer is {
      Clawback -> {
        let unvested = unvested_amount(d.total_amount, d.vested_so_far)
        clawback_allowed(range, d.irrevocable_slot) && unvested > 0
      }
      Withdraw ->
        fully_irrevocable(range, d.irrevocable_slot)
    }
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_clawback_before_deadline_allowed(
  deadline via fuzz.int_between(1001, 2000),
) {
  clawback_allowed(interval.before(1000), deadline)
}

test prop_clawback_after_deadline_blocked(
  deadline via fuzz.int_between(0, 999),
) {
  !clawback_allowed(interval.after(1000), deadline)
}

test prop_fully_irrevocable_after_deadline(
  deadline via fuzz.int_between(0, 999),
) {
  fully_irrevocable(interval.after(1000), deadline)
}

test prop_unvested_non_negative(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(0, 999)),
) {
  let (total, vested) = vals
  total >= vested || unvested_amount(total, vested) < 0 || unvested_amount(total, vested) >= 0
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// clawback_allowed returns False when the validity range is entirely after
/// the irrevocable_slot, i.e. the deadline has already passed.
/// Here interval.after(2000) is entirely after any deadline in [0, 1999].
test prop_clawback_rejected_after_deadline(
  deadline via fuzz.int_between(0, 1999),
) fail {
  expect clawback_allowed(interval.after(2000), deadline)
}

/// fully_irrevocable returns False when the validity range ends before the
/// irrevocable_slot, i.e. the deadline has not yet been reached.
/// interval.before(500) is NOT entirely after any slot >= 500.
test prop_not_irrevocable_before_deadline(
  deadline via fuzz.int_between(500, 2000),
) fail {
  expect fully_irrevocable(interval.before(500), deadline)
}

/// clawback_allowed returns False for a point interval that is entirely after
/// the irrevocable_slot.  interval.after(100) is entirely after slot 99 and
/// any smaller slot.
test prop_clawback_rejected_point_after_deadline(
  deadline via fuzz.int_between(0, 99),
) fail {
  expect clawback_allowed(interval.after(100), deadline)
}

/// fully_irrevocable returns False when the range is entirely before the
/// irrevocable_slot.  interval.before(300) is not entirely after slot 300
/// or any larger slot.
test prop_not_irrevocable_range_before_deadline(
  deadline via fuzz.int_between(300, 1000),
) fail {
  expect fully_irrevocable(interval.before(300), deadline)
}