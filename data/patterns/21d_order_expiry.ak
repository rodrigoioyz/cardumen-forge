use aiken/fuzz
use aiken/interval

/// Order expires after a given slot; execution must happen before expiry
fn order_active(validity_range: interval.Interval, expiry_slot: Int) -> Bool {
  !interval.is_entirely_after(validity_range, expiry_slot)
}

/// Execution requires order to be active
fn execution_valid(
  validity_range: interval.Interval,
  expiry_slot:    Int,
  price_ok:       Bool,
) -> Bool {
  order_active(validity_range, expiry_slot) && price_ok
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_order_active_before_expiry(
  expiry via fuzz.int_between(1001, 2000),
) {
  order_active(interval.before(1000), expiry)
}

test prop_order_inactive_after_expiry(
  expiry via fuzz.int_between(0, 999),
) {
  !order_active(interval.after(1000), expiry)
}

test prop_execution_valid_when_active_and_price_ok(
  expiry via fuzz.int_between(1001, 2000),
) {
  execution_valid(interval.before(1000), expiry, True)
}

test prop_execution_invalid_after_expiry(
  expiry via fuzz.int_between(0, 999),
) {
  !execution_valid(interval.after(1000), expiry, True)
}
