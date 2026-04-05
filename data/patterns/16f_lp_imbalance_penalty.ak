use aiken/fuzz

/// Ratio of the two deposit amounts (scaled by 1000 for precision)
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
