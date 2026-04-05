use aiken/fuzz
use aiken/interval

/// Cliff period: no tokens vest before the cliff slot
fn past_cliff(validity_range: interval.Interval, cliff_slot: Int) -> Bool {
  interval.is_entirely_after(validity_range, cliff_slot)
}

/// After cliff: vested amount is proportional to time elapsed
fn vested_after_cliff(
  total_amount: Int,
  elapsed:      Int,
  total_period: Int,
) -> Int {
  total_amount * elapsed / total_period
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_before_cliff_blocked(
  cliff via fuzz.int_between(1001, 2000),
) {
  !past_cliff(interval.before(1000), cliff)
}

test prop_after_cliff_allowed(
  cliff via fuzz.int_between(0, 999),
) {
  past_cliff(interval.after(1000), cliff)
}

test prop_full_period_vests_all(
  total via fuzz.int_between(1, 100000),
) {
  vested_after_cliff(total, 1000, 1000) == total
}

test prop_zero_elapsed_vests_nothing(
  total via fuzz.int_between(1, 100000),
) {
  vested_after_cliff(total, 0, 1000) == 0
}
