
/// Order expires after a given slot; execution must happen before expiry
use aiken/fuzz
use aiken/interval
use cardano/transaction.{Transaction}
fn order_active(validity_range: interval.Interval, expiry_slot: Int) -> Bool {
  !interval.is_entirely_after(validity_range, expiry_slot)
}

/// Execution requires order to be active
fn execution_valid(
  validity_range: interval.Interval,
  expiry_slot: Int,
  price_ok: Bool,
) -> Bool {
  order_active(validity_range, expiry_slot) && price_ok
}

pub type OrderDatum {
  expiry_slot: Int,
  min_price: Int,
}

pub type OrderRedeemer {
  Execute { offered_price: Int }
  Cancel
}

validator order_expiry {
  spend(
    datum: Option<OrderDatum>,
    redeemer: OrderRedeemer,
    _output_ref: Data,
    self: Transaction,
  ) {
    expect Some(d) = datum
    when redeemer is {
      Execute { offered_price } -> {
        let price_ok = offered_price >= d.min_price
        execution_valid(self.validity_range, d.expiry_slot, price_ok)
      }
      Cancel ->
        !order_active(self.validity_range, d.expiry_slot)
    }
  }

  else(_) {
    fail
  }
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

// ── Negative (fail) tests ─────────────────────────────────────────────────────

/// order_active returns False when the validity range is entirely after expiry_slot.
/// interval.after(1000) means the range starts at 1001+, so any expiry <= 999
/// makes is_entirely_after return True, causing order_active to return False.
test prop_order_active_expired_is_false(
  expiry via fuzz.int_between(0, 999),
) fail {
  expect order_active(interval.after(1000), expiry)
}

/// execution_valid returns False when price_ok is False, regardless of activity.
/// Using an active range (before(1000), expiry > 1000) but price_ok = False
/// guarantees the result is False.
test prop_execution_invalid_bad_price(
  expiry via fuzz.int_between(1001, 2000),
) fail {
  expect execution_valid(interval.before(1000), expiry, False)
}

/// execution_valid returns False when both the order is expired AND price is bad.
/// interval.after(1000) with expiry in [0, 999] means order_active = False,
/// so the conjunction is False regardless of price_ok.
test prop_execution_invalid_expired_and_bad_price(
  expiry via fuzz.int_between(0, 999),
) fail {
  expect execution_valid(interval.after(1000), expiry, False)
}

/// execution_valid returns False when order is expired even if price_ok is True.
/// Duplicate of the existing negative logic but expressed as a fail test to
/// confirm the helper itself rejects — not just that its negation holds.
test prop_execution_invalid_expired_good_price(
  expiry via fuzz.int_between(0, 999),
) fail {
  expect execution_valid(interval.after(1000), expiry, True)
}