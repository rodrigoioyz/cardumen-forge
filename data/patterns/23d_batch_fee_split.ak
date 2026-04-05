use aiken/fuzz

/// Total fee for a batch of N swaps at per-swap fee
fn total_batch_fee(swap_count: Int, per_swap_fee: Int) -> Int {
  swap_count * per_swap_fee
}

/// Fee is split proportionally: each swap contributes per_swap_fee
fn fee_per_swap_correct(
  total_fee:    Int,
  swap_count:   Int,
  per_swap_fee: Int,
) -> Bool {
  swap_count > 0 && total_fee == swap_count * per_swap_fee
}

/// Discount for large batches: batches of >= threshold get reduced fee
fn discounted_fee(swap_count: Int, per_swap_fee: Int, threshold: Int, discount_bps: Int) -> Int {
  if swap_count >= threshold {
    total_batch_fee(swap_count, per_swap_fee) * (10000 - discount_bps) / 10000
  } else {
    total_batch_fee(swap_count, per_swap_fee)
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_fee_scales_with_count(
  vals via fuzz.both(fuzz.int_between(1, 10), fuzz.int_between(1, 1000)),
) {
  let (count, per_fee) = vals
  total_batch_fee(count, per_fee) == count * per_fee
}

test prop_fee_per_swap_correct_construction(
  vals via fuzz.both(fuzz.int_between(1, 10), fuzz.int_between(1, 1000)),
) {
  let (count, per_fee) = vals
  fee_per_swap_correct(total_batch_fee(count, per_fee), count, per_fee)
}

test prop_discount_reduces_fee(
  vals via fuzz.both(fuzz.int_between(5, 20), fuzz.int_between(1, 1000)),
) {
  let (count, per_fee) = vals
  let normal    = total_batch_fee(count, per_fee)
  let discounted = discounted_fee(count, per_fee, 5, 500)
  discounted <= normal
}

test prop_no_discount_below_threshold(
  vals via fuzz.both(fuzz.int_between(1, 4), fuzz.int_between(1, 1000)),
) {
  let (count, per_fee) = vals
  discounted_fee(count, per_fee, 5, 500) == total_batch_fee(count, per_fee)
}
