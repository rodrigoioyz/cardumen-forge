
/// Stability fee accrues on outstanding debt (annual rate in bps, per-block approximation)
use aiken/fuzz
use cardano/transaction.{Transaction, InlineDatum}
use cardano/assets.{PolicyId}
fn accrued_fee(debt: Int, rate_bps: Int, blocks: Int) -> Int {
  debt * rate_bps * blocks / 10000
}

/// Total obligation after fee accrual
fn total_owed(debt: Int, rate_bps: Int, blocks: Int) -> Int {
  debt + accrued_fee(debt, rate_bps, blocks)
}

/// Fee never exceeds the principal for reasonable rates and block counts
fn fee_bounded(debt: Int, rate_bps: Int, blocks: Int, max_multiplier: Int) -> Bool {
  total_owed(debt, rate_bps, blocks) <= debt * max_multiplier
}

// ── Datum / Redeemer ─────────────────────────────────────────────────────────

pub type VaultDatum {
  debt: Int,
  rate_bps: Int,
  last_block: Int,
  max_multiplier: Int,
}

pub type VaultRedeemer {
  current_block: Int,
  repay_amount: Int,
}

// ── Validator ────────────────────────────────────────────────────────────────

validator stable_fee_accrual(policy_id: PolicyId) {
  spend(
    datum: Option<VaultDatum>,
    redeemer: VaultRedeemer,
    _own_ref: Data,
    self: Transaction,
  ) {
    expect Some(vault) = datum
    let blocks_elapsed = redeemer.current_block - vault.last_block
    expect blocks_elapsed >= 0
    let owed = total_owed(vault.debt, vault.rate_bps, blocks_elapsed)
    let repayment_sufficient = redeemer.repay_amount >= owed
    let safe = fee_bounded(vault.debt, vault.rate_bps, blocks_elapsed, vault.max_multiplier)
    let _ = self.inputs
    repayment_sufficient && safe
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_zero_rate_no_fee(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(1, 1000)),
) {
  let (debt, blocks) = vals
  accrued_fee(debt, 0, blocks) == 0
}

test prop_fee_increases_with_blocks(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 100)),
) {
  let (debt, rate) = vals
  accrued_fee(debt, rate, 100) >= accrued_fee(debt, rate, 50)
}

test prop_total_owed_exceeds_principal(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 100)),
) {
  let (debt, rate) = vals
  total_owed(debt, rate, 100) >= debt
}

test prop_fee_bounded_by_multiplier(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(1, 50)),
) {
  let (debt, rate_bps) = vals
  // Over 10 blocks at rate <= 50 bps, max fee = debt*50*10/10000 = 0.5%*debt << 2*debt
  fee_bounded(debt, rate_bps, 10, 2)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// fee_bounded must return False when the rate is astronomically high relative
/// to the multiplier. With rate_bps >= 20001 and blocks=1, max_multiplier=1:
/// total_owed = debt + debt*rate_bps*1/10000 >= debt + 2*debt = 3*debt > debt*1
test prop_fee_bounded_rejected_when_rate_exceeds_multiplier(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(20001, 100000)),
) fail {
  let (debt, rate_bps) = vals
  // max_multiplier=1 means total_owed must be <= debt, impossible with any positive fee
  expect fee_bounded(debt, rate_bps, 1, 1)
}

/// fee_bounded must return False when blocks is very large even at a moderate rate.
/// With debt=1000, rate_bps=100, blocks=100000, max_multiplier=2:
/// accrued = 1000*100*100000/10000 = 1_000_000, total = 1_001_000 >> 2000
test prop_fee_bounded_rejected_when_blocks_too_large(
  blocks via fuzz.int_between(200, 10000),
) fail {
  // debt=1000, rate_bps=100, max_multiplier=1:
  // accrued = 1000*100*blocks/10000 = 10*blocks >= 2000 for blocks>=200
  // total_owed = 1000 + 10*blocks >= 3000 > 1000*1
  expect fee_bounded(1000, 100, blocks, 1)
}

/// fee_bounded with max_multiplier=0 always fails because total_owed >= debt > 0 = debt*0
test prop_fee_bounded_rejected_when_multiplier_zero(
  vals via fuzz.both(fuzz.int_between(1, 10000), fuzz.int_between(0, 1000)),
) fail {
  let (debt, blocks) = vals
  // debt*0 = 0, but total_owed >= debt >= 1, so always False
  expect fee_bounded(debt, 0, blocks, 0)
}

/// fee_bounded fails when rate_bps pushes total_owed above debt*max_multiplier.
/// With debt=500, rate_bps=10000 (100%), blocks=1, max_multiplier=1:
/// accrued = 500*10000*1/10000 = 500, total = 1000 > 500*1
test prop_fee_bounded_rejected_full_rate_one_block() fail {
  // 100% rate per block, multiplier capped at 1 — always fails
  expect fee_bounded(500, 10000, 1, 1)
}