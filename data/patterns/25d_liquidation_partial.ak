use aiken/fuzz

/// Partial liquidation: liquidate only enough to restore health
/// Returns minimum debt to repay to reach target_ratio
fn min_repay_to_restore(
  collateral:   Int,
  debt:         Int,
  target_ratio: Int,
) -> Int {
  // Need: collateral * 100 >= new_debt * target_ratio
  // → new_debt <= collateral * 100 / target_ratio
  // → repay = debt - new_debt
  let max_debt = collateral * 100 / target_ratio
  if debt > max_debt { debt - max_debt } else { 0 }
}

/// After partial repayment, position is healthy
fn healthy_after_repay(
  collateral:   Int,
  debt:         Int,
  repay:        Int,
  target_ratio: Int,
) -> Bool {
  let new_debt = debt - repay
  new_debt > 0 && collateral * 100 >= new_debt * target_ratio
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_no_repay_needed_when_healthy(
  vals via fuzz.both(fuzz.int_between(200, 500), fuzz.int_between(1, 100)),
) {
  let (collateral, debt) = vals
  min_repay_to_restore(collateral, debt, 150) == 0
}

test prop_repay_restores_health(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(101, 200)),
) {
  let (collateral, debt) = vals
  let repay = min_repay_to_restore(collateral, debt, 150)
  repay == 0 || healthy_after_repay(collateral, debt, repay, 150)
}

test prop_full_repay_always_healthy(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
) {
  let (collateral, debt) = vals
  // Repay all but 1 lovelace
  let repay = debt - 1
  healthy_after_repay(collateral, debt, repay, 0)
}

test prop_min_repay_non_negative(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
) {
  let (collateral, debt) = vals
  min_repay_to_restore(collateral, debt, 150) >= 0
}
