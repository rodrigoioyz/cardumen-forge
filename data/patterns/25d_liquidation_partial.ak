use aiken/fuzz
use cardano/transaction.{Transaction, OutputReference}
use aiken/collection/list
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
  new_debt >= 0 && collateral * 100 >= new_debt * target_ratio
}

pub type LiquidationDatum {
  collateral: Int,
  debt: Int,
  target_ratio: Int,
  owner: ByteArray,
}

pub type LiquidationRedeemer {
  repay_amount: Int,
}

validator partial_liquidation {
  spend(
    datum: Option<LiquidationDatum>,
    redeemer: LiquidationRedeemer,
    _ref: OutputReference,
    self: Transaction,
  ) {
    expect Some(d) = datum
    let repay = redeemer.repay_amount
    let min_repay = min_repay_to_restore(d.collateral, d.debt, d.target_ratio)
    let position_restored =
      healthy_after_repay(d.collateral, d.debt, repay, d.target_ratio)
    let repay_sufficient = repay >= min_repay
    let signed_by_owner =
      list.any(self.extra_signatories, fn(sig) { sig == d.owner })
    repay_sufficient && position_restored && signed_by_owner
  }

  else(_) {
    fail
  }
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

// ── Negative / fail tests ────────────────────────────────────────────────────

// Repaying more than the full debt makes new_debt negative → healthy_after_repay
// returns False because new_debt >= 0 is violated.
test prop_overrepay_unhealthy(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(1, 500)),
) fail {
  let (collateral, debt) = vals
  // repay = debt + 1  →  new_debt = -1  →  new_debt >= 0 is False
  expect healthy_after_repay(collateral, debt, debt + 1, 150)
}

// Collateral = 1, debt is large, repay = 0:
// new_debt = debt, collateral*100 = 100 < debt*150 for any debt >= 1
// So healthy_after_repay returns False.
test prop_undercollateralized_no_repay_unhealthy(
  debt via fuzz.int_between(2, 1000),
) fail {
  // 1 * 100 = 100, debt * 150 >= 300  →  unhealthy
  expect healthy_after_repay(1, debt, 0, 150)
}

// Zero repay on a severely undercollateralized position:
// collateral=1, debt=200, repay=0, target_ratio=150
// new_debt=200, 1*100=100 < 200*150=30000 → False
test unit_zero_repay_unhealthy() fail {
  expect healthy_after_repay(1, 200, 0, 150)
}

// Repay that is one unit short of what is needed:
// collateral=10, target_ratio=150 → max_debt = 10*100/150 = 6
// min_repay = debt - 6; repaying (min_repay - 1) leaves new_debt = 7
// 10*100=1000 < 7*150=1050 → False
test unit_insufficient_repay_unhealthy() fail {
  let collateral = 10
  let debt = 20
  let target_ratio = 150
  let min_repay = min_repay_to_restore(collateral, debt, target_ratio)
  expect healthy_after_repay(collateral, debt, min_repay - 1, target_ratio)
}