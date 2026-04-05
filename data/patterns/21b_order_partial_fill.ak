
/// Partial fill: filled <= order_qty, remaining = order_qty - filled
use aiken/fuzz
use cardano/transaction.{Transaction, InlineDatum}
use cardano/assets
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

// ── Datum / Redeemer ─────────────────────────────────────────────────────────

pub type OrderDatum {
  order_qty: Int,
}

pub type FillRedeemer {
  filled: Int,
}

// ── Validator ────────────────────────────────────────────────────────────────

validator order_partial_fill {
  spend(
    datum: Option<OrderDatum>,
    redeemer: FillRedeemer,
    _output_ref: Data,
    self: Transaction,
  ) {
    expect Some(d) = datum
    let filled = redeemer.filled
    let qty = d.order_qty
    expect partial_fill_valid(filled, qty)
    let rem = remaining_qty(filled, qty)
    if is_full_fill(filled, qty) {
      rem == 0
    } else {
      rem > 0
    }
  }

  else(_) {
    fail
  }
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

// ── Negative fail tests ───────────────────────────────────────────────────────

/// Zero fill is never valid — partial_fill_valid requires filled > 0
test prop_fail_zero_fill(
  qty via fuzz.int_between(1, 1000),
) fail {
  expect partial_fill_valid(0, qty)
}

/// Negative fill is never valid — partial_fill_valid requires filled > 0
test prop_fail_negative_fill(
  vals via fuzz.both(fuzz.int_between(-1000, -1), fuzz.int_between(1, 1000)),
) fail {
  let (filled, qty) = vals
  expect partial_fill_valid(filled, qty)
}

/// Overfill: filled strictly greater than order_qty is always invalid
test prop_fail_overfill(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(1, 500)),
) fail {
  let (qty, extra) = vals
  // filled = qty + extra > qty, so partial_fill_valid must return False
  expect partial_fill_valid(qty + extra, qty)
}

/// is_full_fill returns False when filled != order_qty (filled < order_qty)
test prop_fail_not_full_fill(
  vals via fuzz.both(fuzz.int_between(1, 99), fuzz.int_between(100, 1000)),
) fail {
  let (filled, qty) = vals
  // filled < qty so is_full_fill must return False
  expect is_full_fill(filled, qty)
}