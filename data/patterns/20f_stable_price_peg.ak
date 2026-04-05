
/// Peg check: oracle price must be within band of target (in bps)
use aiken/fuzz
use cardano/transaction.{Transaction}
fn within_peg_band(
  oracle_price: Int,
  target_price: Int,
  band_bps: Int,
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

// ── Validator ────────────────────────────────────────────────────────────────

pub type PegDatum {
  target_price: Int,
  band_bps: Int,
}

pub type PegRedeemer {
  oracle_price: Int,
}

validator stable_price_peg {
  spend(
    datum: Option<PegDatum>,
    redeemer: PegRedeemer,
    _output_ref: Data,
    _self: Transaction,
  ) {
    expect Some(d) = datum
    let max_dev = max_deviation(d.target_price, d.band_bps)
    let price_ok = within_peg_band(redeemer.oracle_price, d.target_price, d.band_bps)
    price_ok && max_dev >= 0
  }

  else(_) {
    fail
  }
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Oracle price is far above the target by at least 10x the target itself,
/// with a tiny band (1–10 bps). Deviation >> band, so within_peg_band is False.
test prop_oracle_way_above_target_rejected(
  vals via fuzz.both(fuzz.int_between(1, 10), fuzz.int_between(1000, 5000)),
) fail {
  let (band_bps, target) = vals
  // oracle_price = target * 2 → deviation = target, which is 10000 bps > band_bps (≤10)
  expect within_peg_band(target * 2, target, band_bps)
}

/// Oracle price is far below the target (oracle = 1, target is large),
/// with a small band. Deviation is massive relative to band.
test prop_oracle_way_below_target_rejected(
  vals via fuzz.both(fuzz.int_between(1, 50), fuzz.int_between(10000, 100000)),
) fail {
  let (band_bps, target) = vals
  // oracle = 1, target is 10000–100000: deviation ≈ target >> any reasonable band
  expect within_peg_band(1, target, band_bps)
}

/// Band is zero bps: only an exact match can satisfy the check, but oracle ≠ target.
/// Any non-zero deviation with band_bps=0 → deviation*10000 > 0 = target*0, so False.
test prop_zero_band_non_exact_price_rejected(
  offset via fuzz.int_between(1, 99999),
) fail {
  let target = 100000
  // oracle differs from target by `offset`, band is 0 → always outside peg
  expect within_peg_band(target + offset, target, 0)
}

/// Price is exactly half the target with a tight band (1–100 bps).
/// Deviation = target/2, which is 5000 bps — always larger than band ≤ 100 bps.
test prop_half_price_always_out_of_band(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(2, 10000)),
) fail {
  let (band_bps, half_target) = vals
  let target = half_target * 2
  // oracle = half_target → deviation = half_target = target/2 = 5000 bps > band_bps
  expect within_peg_band(half_target, target, band_bps)
}