
/// Ratio of the two deposit amounts (scaled by 1000 for precision)
use aiken/fuzz
use cardano/transaction.{InlineDatum, Output, Transaction}
fn deposit_ratio(input_a: Int, input_b: Int) -> Int {
  input_a * 1000 / input_b
}

/// Ideal ratio matches pool reserves
fn ideal_ratio(reserve_a: Int, reserve_b: Int) -> Int {
  reserve_a * 1000 / reserve_b
}

/// Imbalance: absolute difference between actual and ideal ratios
fn imbalance(input_a: Int, input_b: Int, reserve_a: Int, reserve_b: Int) -> Int {
  let actual = deposit_ratio(input_a, input_b)
  let ideal  = ideal_ratio(reserve_a, reserve_b)
  if actual >= ideal { actual - ideal } else { ideal - actual }
}

/// Deposit is balanced if imbalance stays within tolerance (in ratio units)
fn is_balanced(
  input_a:   Int,
  input_b:   Int,
  reserve_a: Int,
  reserve_b: Int,
  tolerance: Int,
) -> Bool {
  imbalance(input_a, input_b, reserve_a, reserve_b) <= tolerance
}

// ── Datum / Redeemer types ───────────────────────────────────────────────────

pub type PoolDatum {
  reserve_a: Int,
  reserve_b: Int,
  tolerance: Int,
}

pub type DepositRedeemer {
  input_a: Int,
  input_b: Int,
}

// ── Validator ────────────────────────────────────────────────────────────────

validator lp_imbalance_penalty {
  spend(
    datum: Option<PoolDatum>,
    redeemer: DepositRedeemer,
    _own_ref: Data,
    _self: Transaction,
  ) {
    when datum is {
      None -> False
      Some(pool) -> {
        let DepositRedeemer { input_a, input_b } = redeemer
        let PoolDatum { reserve_a, reserve_b, tolerance } = pool
        expect input_a > 0
        expect input_b > 0
        is_balanced(input_a, input_b, reserve_a, reserve_b, tolerance)
      }
    }
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_equal_inputs_at_equal_reserves_zero_imbalance(
  n via fuzz.int_at_least(1),
) {
  imbalance(n, n, n, n) == 0
}

test prop_balanced_deposit_accepted(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(10, 50)),
) {
  let (reserve, tolerance) = vals
  is_balanced(reserve, reserve, reserve, reserve, tolerance)
}

test prop_extreme_imbalance_rejected(
  reserve via fuzz.int_between(2, 100),
) {
  // deposit 1:100 against 1:1 pool — very unbalanced
  !is_balanced(1, 100, reserve, reserve, 10)
}

test prop_imbalance_non_negative(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(1, 500)),
) {
  let (a, b) = vals
  imbalance(a, b, 100, 100) >= 0
}

// ── Negative (fail) property tests ──────────────────────────────────────────

/// A deposit of 1:1000 against a perfectly balanced 1:1 pool with zero
/// tolerance is always severely imbalanced — is_balanced must return False.
test prop_severe_imbalance_zero_tolerance_rejected(
  reserve via fuzz.int_between(1, 200),
) fail {
  // actual ratio = 1*1000/1000 = 1, ideal ratio = reserve*1000/reserve = 1000
  // imbalance = 999, tolerance = 0  →  999 <= 0 is False
  expect is_balanced(1, 1000, reserve, reserve, 0)
}

/// When input_b is much larger than input_a against a 1:1 pool, the imbalance
/// will always exceed a very tight tolerance of 1.
test prop_lopsided_deposit_tight_tolerance_rejected(
  vals via fuzz.both(fuzz.int_between(1, 10), fuzz.int_between(500, 1000)),
) fail {
  let (small, large) = vals
  // actual ratio = small*1000/large  (very small, e.g. 2..20)
  // ideal ratio  = 100*1000/100 = 1000
  // imbalance >= 980, tolerance = 1  →  always False
  expect is_balanced(small, large, 100, 100, 1)
}

/// Depositing with a heavily skewed ratio (100:1) into a 1:1 pool with
/// tolerance capped at 50 is always rejected.
test prop_high_ratio_deposit_rejected(
  reserve via fuzz.int_between(1, 100),
) fail {
  // actual = 100*1000/1 = 100000, ideal = reserve*1000/reserve = 1000
  // imbalance = 99000, tolerance = 50  →  always False
  expect is_balanced(100, 1, reserve, reserve, 50)
}

/// A deposit that perfectly mirrors one side of the pool but is far from the
/// ideal ratio (2:1 pool, depositing 1:100) never fits within tolerance = 10.
test prop_mismatched_pool_ratio_rejected(
  vals via fuzz.both(fuzz.int_between(1, 5), fuzz.int_between(50, 100)),
) fail {
  // pool reserve ratio is 2:1 → ideal = 2000
  // actual = small*1000/large  (e.g. max 5*1000/50 = 100)
  // imbalance >= 1900, tolerance = 10  →  always False
  let (small, large) = vals
  expect is_balanced(small, large, 200, 100, 10)
}