use aiken/fuzz
use aiken/interval

/// Revocable vesting: employer can claw back unvested tokens before a deadline
fn unvested_amount(
  total_amount: Int,
  vested_so_far: Int,
) -> Int {
  total_amount - vested_so_far
}

/// Clawback is valid only before the irrevocability deadline
fn clawback_allowed(
  validity_range:   interval.Interval,
  irrevocable_slot: Int,
) -> Bool {
  !interval.is_entirely_after(validity_range, irrevocable_slot)
}

/// After deadline: vesting is irrevocable
fn fully_irrevocable(
  validity_range:   interval.Interval,
  irrevocable_slot: Int,
) -> Bool {
  interval.is_entirely_after(validity_range, irrevocable_slot)
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
