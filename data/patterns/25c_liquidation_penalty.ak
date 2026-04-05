
/// Liquidation penalty: liquidator pays debt and receives collateral + bonus
use aiken/fuzz
use aiken/collection/list
use cardano/assets
use cardano/transaction.{Transaction, OutputReference}
fn liquidation_bonus(collateral: Int, bonus_bps: Int) -> Int {
  collateral * bonus_bps / 10000
}

/// Liquidator receives: collateral + bonus
fn liquidator_receives(collateral: Int, bonus_bps: Int) -> Int {
  collateral + liquidation_bonus(collateral, bonus_bps)
}

/// Bonus is non-negative and bounded
fn bonus_in_range(collateral: Int, bonus_bps: Int) -> Bool {
  bonus_bps >= 0 && bonus_bps < 10000
    && liquidation_bonus(collateral, bonus_bps) >= 0
}

pub type LiquidationDatum {
  collateral_lovelace: Int,
  bonus_bps: Int,
  borrower: ByteArray,
  liquidator: ByteArray,
}

pub type LiquidationRedeemer {
  Liquidate
}

validator liquidation_vault {
  spend(
    datum: Option<LiquidationDatum>,
    _redeemer: LiquidationRedeemer,
    _ref: OutputReference,
    self: Transaction,
  ) {
    expect Some(d) = datum
    let valid_bonus = bonus_in_range(d.collateral_lovelace, d.bonus_bps)
    let min_payout = liquidator_receives(d.collateral_lovelace, d.bonus_bps)
    let liquidator_signed =
      list.any(self.extra_signatories, fn(sig) { sig == d.liquidator })
    let liquidator_paid_enough =
      list.any(
        self.outputs,
        fn(output) {
          assets.lovelace_of(output.value) >= min_payout
        },
      )
    valid_bonus && liquidator_signed && liquidator_paid_enough
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_zero_bonus_receives_exact_collateral(
  collateral via fuzz.int_between(1, 100000),
) {
  liquidator_receives(collateral, 0) == collateral
}

test prop_bonus_increases_proceeds(
  vals via fuzz.both(fuzz.int_between(10000, 100000), fuzz.int_between(1, 500)),
) {
  let (collateral, bonus_bps) = vals
  liquidator_receives(collateral, bonus_bps) > collateral
}

test prop_bonus_non_negative(
  vals via fuzz.both(fuzz.int_between(1, 100000), fuzz.int_between(0, 500)),
) {
  let (collateral, bonus_bps) = vals
  liquidation_bonus(collateral, bonus_bps) >= 0
}

test prop_bonus_in_range_valid(
  collateral via fuzz.int_between(1, 100000),
) {
  bonus_in_range(collateral, 500)
}

// ── Negative / fail tests ─────────────────────────────────────────────────────

/// bonus_bps >= 10000 means the check bonus_bps < 10000 fails,
/// so bonus_in_range must always return False.
test prop_bonus_bps_at_or_above_max_rejected(
  vals via fuzz.both(fuzz.int_between(1, 100000), fuzz.int_between(10000, 50000)),
) fail {
  let (collateral, bonus_bps) = vals
  expect bonus_in_range(collateral, bonus_bps)
}

/// Negative bonus_bps violates bonus_bps >= 0,
/// so bonus_in_range must always return False.
test prop_negative_bonus_bps_rejected(
  vals via fuzz.both(fuzz.int_between(1, 100000), fuzz.int_between(-10000, -1)),
) fail {
  let (collateral, bonus_bps) = vals
  expect bonus_in_range(collateral, bonus_bps)
}

/// Negative collateral with a positive bonus_bps produces a negative bonus,
/// violating liquidation_bonus(...) >= 0, so bonus_in_range returns False.
test prop_negative_collateral_with_positive_bonus_rejected(
  vals via fuzz.both(fuzz.int_between(-100000, -1), fuzz.int_between(1, 9999)),
) fail {
  let (collateral, bonus_bps) = vals
  expect bonus_in_range(collateral, bonus_bps)
}

/// bonus_bps exactly equal to 10000 is not strictly less than 10000,
/// so bonus_in_range returns False regardless of collateral.
test prop_bonus_bps_exactly_10000_rejected(
  collateral via fuzz.int_between(1, 100000),
) fail {
  expect bonus_in_range(collateral, 10000)
}