use aiken/fuzz

/// Peg check: oracle price must be within band of target (in bps)
fn within_peg_band(
  oracle_price: Int,
  target_price: Int,
  band_bps:     Int,
) -> Bool {
  let deviation = if oracle_price >= target_price {
    oracle_price - target_price
  } else {
    target_price - oracle_price
  }
  deviation * 10000 <= target_price * band_bps
}

/// Maximum allowed deviation from peg
fn max_deviation(target_price: Int, band_bps: Int) -> Int {
  target_price * band_bps / 10000
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_exact_peg_is_valid(
  price via fuzz.int_between(1000, 100000),
) {
  within_peg_band(price, price, 200)
}

test prop_within_band_valid(
  vals via fuzz.both(fuzz.int_between(990, 1010), fuzz.int_between(100, 200)),
) {
  // target = 1000, band = band_bps → max_dev = band_bps/10 for target=1000
  let (price, band_bps) = vals
  let target = 1000
  let max_dev = max_deviation(target, band_bps)
  let actual_dev = if price >= target { price - target } else { target - price }
  actual_dev <= max_dev || !within_peg_band(price, target, band_bps)
}

test prop_far_from_peg_rejected(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(100, 200)),
) {
  let (band_bps, offset) = vals
  // price = 1000 + 1000 >> far above band
  !within_peg_band(1000 + offset * 100, 1000, band_bps)
}

test prop_max_deviation_non_negative(
  vals via fuzz.both(fuzz.int_between(1, 10000), fuzz.int_between(1, 500)),
) {
  let (target, band) = vals
  max_deviation(target, band) >= 0
}
