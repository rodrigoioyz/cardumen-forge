use aiken/collection/list
use aiken/fuzz
use cardano/transaction.{Transaction}

/// Batch liquidation: process multiple positions, count how many are liquidatable
fn count_liquidatable(
  positions: List<(Int, Int)>,
  threshold: Int,
) -> Int {
  list.foldl(
    positions,
    0,
    fn(pos, acc) {
      let (collateral, debt) = pos
      let hf = collateral * 100 / debt
      if hf < threshold { acc + 1 } else { acc }
    },
  )
}

/// All positions in the batch must be liquidatable
fn all_liquidatable(positions: List<(Int, Int)>, threshold: Int) -> Bool {
  count_liquidatable(positions, threshold) == list.length(positions)
}

// ── Validator ─────────────────────────────────────────────────────────────────

pub type LiquidationDatum {
  positions: List<(Int, Int)>,
  threshold: Int,
}

pub type LiquidationRedeemer {
  min_liquidatable: Int,
}

validator liquidation_batch {
  spend(
    datum: Option<LiquidationDatum>,
    redeemer: LiquidationRedeemer,
    _output_ref: Data,
    _self: Transaction,
  ) {
    expect Some(d) = datum
    let liquidatable = count_liquidatable(d.positions, d.threshold)
    let meets_minimum = liquidatable >= redeemer.min_liquidatable
    let batch_valid = all_liquidatable(d.positions, d.threshold)
    meets_minimum || batch_valid
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_undercollateralised_counted(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(101, 200)),
) {
  let (collateral, debt) = vals
  count_liquidatable([(collateral, debt)], 150) == 1
}

test prop_overcollateralised_not_counted(
  vals via fuzz.both(fuzz.int_between(200, 500), fuzz.int_between(1, 100)),
) {
  let (collateral, debt) = vals
  count_liquidatable([(collateral, debt)], 150) == 0
}

test prop_empty_batch_zero_count() {
  count_liquidatable([], 150) == 0
}

test prop_all_liquidatable_batch(
  vals via fuzz.both(fuzz.int_between(1, 50), fuzz.int_between(100, 200)),
) {
  let (collateral, debt) = vals
  all_liquidatable([(collateral, debt), (collateral, debt)], 150)
}