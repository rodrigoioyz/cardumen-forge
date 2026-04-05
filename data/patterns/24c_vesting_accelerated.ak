use aiken/collection/list
use aiken/fuzz

/// Accelerated vesting: upon a trigger event, all remaining tranches vest immediately
fn accelerated_vested(
  total_amount:    Int,
  already_claimed: Int,
) -> Int {
  total_amount - already_claimed
}

/// Normal vesting: only tranches up to current index are claimable
fn normal_vested(
  total_amount:   Int,
  current_idx:    Int,
  total_tranches: Int,
) -> Int {
  list.foldl(
    list.range(0, current_idx - 1),
    0,
    fn(i, acc) {
      let tranche = total_amount / total_tranches + (if i < total_amount % total_tranches { 1 } else { 0 })
      acc + tranche
    },
  )
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_accelerated_with_no_claims(
  total via fuzz.int_between(1, 100000),
) {
  accelerated_vested(total, 0) == total
}

test prop_accelerated_after_partial_claim(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(1, 99)),
) {
  let (total, claimed) = vals
  accelerated_vested(total, claimed) == total - claimed
}

test prop_normal_vested_all_tranches(
  vals via fuzz.both(fuzz.int_between(10, 1000), fuzz.int_between(1, 10)),
) {
  let (total, n) = vals
  normal_vested(total, n, n) == total
}

test prop_normal_vested_zero_tranches_elapsed(
  vals via fuzz.both(fuzz.int_between(10, 1000), fuzz.int_between(1, 10)),
) {
  let (total, n) = vals
  normal_vested(total, 0, n) == 0
}
