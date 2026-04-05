use aiken/collection/list
use aiken/fuzz
use cardano/transaction.{Transaction}

/// Rollup: aggregate total input and total output for a batch of swaps
/// Returns (total_in, total_out)
fn batch_totals(
  swaps: List<(Int, Int)>,
) -> (Int, Int) {
  list.foldl(
    swaps,
    (0, 0),
    fn(swap, acc) {
      let (total_in, total_out) = acc
      let (swap_in, swap_out)   = swap
      (total_in + swap_in, total_out + swap_out)
    },
  )
}

/// All swaps are individually positive
fn all_positive(swaps: List<(Int, Int)>) -> Bool {
  list.all(swaps, fn(s) {
    let (in_, out) = s
    in_ > 0 && out > 0
  })
}

/// Net rollup: total_out >= min_total_out
fn rollup_ok(swaps: List<(Int, Int)>, min_total_out: Int) -> Bool {
  let (_, total_out) = batch_totals(swaps)
  total_out >= min_total_out
}

// ── Redeemer type ────────────────────────────────────────────────────────────

pub type BatchRedeemer {
  swaps: List<(Int, Int)>,
  min_total_out: Int,
}

// ── Validator ────────────────────────────────────────────────────────────────

validator batch_rollup {
  mint(redeemer: BatchRedeemer, _policy_id: ByteArray, _self: Transaction) {
    let BatchRedeemer { swaps, min_total_out } = redeemer
    // Ensure every swap has positive in/out values
    expect all_positive(swaps)
    // Ensure total output across the batch meets the minimum threshold
    expect rollup_ok(swaps, min_total_out)
    // Also verify the batch is non-empty
    let (total_in, _) = batch_totals(swaps)
    total_in > 0
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_batch_totals_sum_correctly(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
) {
  let (a, b) = vals
  let swaps = [(a, b), (a, b)]
  batch_totals(swaps) == (a * 2, b * 2)
}

test prop_empty_batch_totals_zero() {
  batch_totals([]) == (0, 0)
}

test prop_all_positive_valid(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 1000)),
) {
  let (a, b) = vals
  all_positive([(a, b), (1, 1)])
}

test prop_rollup_ok_when_total_sufficient(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(1, 500)),
) {
  let (out1, out2) = vals
  let swaps = [(1, out1), (1, out2)]
  rollup_ok(swaps, out1 + out2)
}