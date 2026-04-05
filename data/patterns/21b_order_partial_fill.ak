use aiken/fuzz

/// Partial fill: filled <= order_qty, remaining = order_qty - filled
fn partial_fill_valid(filled: Int, order_qty: Int) -> Bool {
  filled > 0 && filled <= order_qty
}

/// Remaining quantity after partial fill
fn remaining_qty(filled: Int, order_qty: Int) -> Int {
  order_qty - filled
}

/// Full fill: filled == order_qty, remaining == 0
fn is_full_fill(filled: Int, order_qty: Int) -> Bool {
  filled == order_qty
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_partial_fill_valid(
  vals via fuzz.both(fuzz.int_between(1, 99), fuzz.int_between(100, 1000)),
) {
  let (filled, qty) = vals
  partial_fill_valid(filled, qty) && remaining_qty(filled, qty) > 0
}

test prop_full_fill_valid(
  qty via fuzz.int_between(1, 1000),
) {
  partial_fill_valid(qty, qty) && is_full_fill(qty, qty)
}

test prop_overfill_rejected(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 100)),
) {
  let (qty, extra) = vals
  !partial_fill_valid(qty + extra, qty)
}

test prop_zero_fill_rejected(
  qty via fuzz.int_between(1, 1000),
) {
  !partial_fill_valid(0, qty)
}
