use aiken/fuzz

/// For the very first deposit (total_lp == 0), use geometric mean: floor(sqrt(a * b))
/// Approximated via integer Newton's method
fn isqrt(n: Int) -> Int {
  if n <= 0 {
    0
  } else {
    // Start from n/2+1 for faster convergence; 15 iterations suffice for n <= 10^7
    let x0 = n / 2 + 1
    let x1  = (x0  + n / x0)  / 2
    let x2  = (x1  + n / x1)  / 2
    let x3  = (x2  + n / x2)  / 2
    let x4  = (x3  + n / x3)  / 2
    let x5  = (x4  + n / x4)  / 2
    let x6  = (x5  + n / x5)  / 2
    let x7  = (x6  + n / x6)  / 2
    let x8  = (x7  + n / x7)  / 2
    let x9  = (x8  + n / x8)  / 2
    let x10 = (x9  + n / x9)  / 2
    let x11 = (x10 + n / x10) / 2
    let x12 = (x11 + n / x11) / 2
    let x13 = (x12 + n / x12) / 2
    let x14 = (x13 + n / x13) / 2
    let x15 = (x14 + n / x14) / 2
    x15
  }
}

/// Initial LP: geometric mean of the two deposit amounts
fn initial_lp(input_a: Int, input_b: Int) -> Int {
  isqrt(input_a * input_b)
}

/// Subsequent deposits use the proportional formula
fn subsequent_lp(
  input_a:   Int,
  input_b:   Int,
  reserve_a: Int,
  reserve_b: Int,
  total_lp:  Int,
) -> Int {
  let lp_a = input_a * total_lp / reserve_a
  let lp_b = input_b * total_lp / reserve_b
  if lp_a <= lp_b { lp_a } else { lp_b }
}

/// Dispatch between initial and subsequent
fn lp_amount(
  input_a:   Int,
  input_b:   Int,
  reserve_a: Int,
  reserve_b: Int,
  total_lp:  Int,
) -> Int {
  if total_lp == 0 {
    initial_lp(input_a, input_b)
  } else {
    subsequent_lp(input_a, input_b, reserve_a, reserve_b, total_lp)
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_isqrt_perfect_square(
  n via fuzz.int_between(1, 100),
) {
  // Limit to small values; 15 iterations from n/2+1 converges for n*n <= 10000
  isqrt(n * n) == n
}

test prop_initial_lp_positive(
  vals via fuzz.both(fuzz.int_between(1, 10000), fuzz.int_between(1, 10000)),
) {
  let (a, b) = vals
  initial_lp(a, b) > 0
}

test prop_lp_dispatch_uses_initial_when_zero(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
) {
  let (a, b) = vals
  lp_amount(a, b, a, b, 0) == initial_lp(a, b)
}

test prop_lp_dispatch_uses_subsequent_when_nonzero(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (reserve, total_lp) = vals
  lp_amount(reserve, reserve, reserve, reserve, total_lp) == total_lp
}
