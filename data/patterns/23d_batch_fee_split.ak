
/// Total fee for a batch of N swaps at per-swap fee
use aiken/fuzz
use cardano/transaction.{Transaction}
fn total_batch_fee(swap_count: Int, per_swap_fee: Int) -> Int {
  swap_count * per_swap_fee
}

/// Fee is split proportionally: each swap contributes per_swap_fee
fn fee_per_swap_correct(
  total_fee: Int,
  swap_count: Int,
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

pub type BatchFeeDatum {
  swap_count: Int,
  per_swap_fee: Int,
  threshold: Int,
  discount_bps: Int,
}

pub type BatchFeeRedeemer {
  claimed_fee: Int,
}

validator batch_fee_split {
  spend(
    datum: Option<BatchFeeDatum>,
    redeemer: BatchFeeRedeemer,
    _output_reference: Data,
    _self: Transaction,
  ) {
    expect Some(d) = datum
    let expected_fee =
      discounted_fee(d.swap_count, d.per_swap_fee, d.threshold, d.discount_bps)
    let split_valid =
      fee_per_swap_correct(
        total_batch_fee(d.swap_count, d.per_swap_fee),
        d.swap_count,
        d.per_swap_fee,
      )
    split_valid && redeemer.claimed_fee == expected_fee
  }

  else(_) {
    fail
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// swap_count == 0 always makes fee_per_swap_correct return False
/// because the guard `swap_count > 0` fails
test prop_zero_swap_count_rejected(
  per_fee via fuzz.int_between(1, 10000),
) fail {
  expect fee_per_swap_correct(0, 0, per_fee)
}

/// A wrong total_fee (one more than correct) must be rejected
/// for any positive swap_count and per_swap_fee
test prop_wrong_total_fee_rejected(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(1, 1000)),
) fail {
  let (count, per_fee) = vals
  // total_fee is off by 1, so equality check always fails
  expect fee_per_swap_correct(count * per_fee + 1, count, per_fee)
}

/// Negative swap_count: swap_count > 0 is False, so always rejected
test prop_negative_swap_count_rejected(
  vals via fuzz.both(fuzz.int_between(-1000, -1), fuzz.int_between(1, 1000)),
) fail {
  let (count, per_fee) = vals
  expect fee_per_swap_correct(count * per_fee, count, per_fee)
}

/// total_fee deliberately understated (half the real fee):
/// equality check always fails for per_fee >= 2
test prop_understated_total_fee_rejected(
  vals via fuzz.both(fuzz.int_between(2, 50), fuzz.int_between(2, 500)),
) fail {
  let (count, per_fee) = vals
  // supply only half the required total — never equals count * per_fee
  expect fee_per_swap_correct(count * per_fee / 2, count, per_fee)
}