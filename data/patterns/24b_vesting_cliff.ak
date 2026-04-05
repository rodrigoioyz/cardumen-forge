
/// Cliff period: no tokens vest before the cliff slot
use aiken/fuzz
use aiken/interval
use cardano/transaction.{Transaction}
fn past_cliff(validity_range: interval.Interval, cliff_slot: Int) -> Bool {
  interval.is_entirely_after(validity_range, cliff_slot)
}

/// After cliff: vested amount is proportional to time elapsed
fn vested_after_cliff(
  total_amount: Int,
  elapsed: Int,
  total_period: Int,
) -> Int {
  total_amount * elapsed / total_period
}

pub type VestingDatum {
  cliff_slot: Int,
  total_amount: Int,
  total_period: Int,
  elapsed: Int,
  beneficiary: ByteArray,
}

validator vesting_cliff {
  spend(
    datum: Option<VestingDatum>,
    _redeemer: Data,
    _utxo: Data,
    self: Transaction,
  ) {
    expect Some(d) = datum
    let cliff_passed = past_cliff(self.validity_range, d.cliff_slot)
    let amount = vested_after_cliff(d.total_amount, d.elapsed, d.total_period)
    let sufficient = amount > 0
    cliff_passed && sufficient
  }

  else(_) {
    fail
  }
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A validity range entirely before the cliff must be rejected.
/// interval.before(500) ends at 500; cliff_slot in [501, 2000] means
/// the range is NOT entirely after the cliff, so past_cliff returns False.
test prop_before_cliff_past_cliff_fails(
  cliff via fuzz.int_between(501, 2000),
) fail {
  expect past_cliff(interval.before(500), cliff)
}

/// A point interval (between x x) is not entirely after cliff when cliff >= x,
/// so past_cliff must return False.
test prop_at_cliff_not_past(
  slot via fuzz.int_between(0, 1000),
) fail {
  // cliff_slot equals slot: the range is NOT strictly after the cliff
  expect past_cliff(interval.between(slot, slot), slot)
}

/// Zero total_amount means nothing ever vests regardless of elapsed/period.
/// vested_after_cliff(0, elapsed, period) == 0, which is NOT > 0,
/// so treating it as Bool via expect will always fail.
test prop_zero_total_amount_vests_nothing(
  elapsed via fuzz.int_between(1, 1000),
) fail {
  // 0 * elapsed / 1000 == 0; expect (0 > 0) fails
  expect vested_after_cliff(0, elapsed, 1000) > 0
}

/// When elapsed is zero the vested amount is always zero, even for large totals.
/// expect (0 > 0) always fails at runtime.
test prop_zero_elapsed_never_sufficient(
  total via fuzz.int_between(1, 1000000),
) fail {
  expect vested_after_cliff(total, 0, 1000) > 0
}