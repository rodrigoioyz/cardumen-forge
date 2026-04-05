use aiken/collection/list
use aiken/fuzz

/// Each beneficiary has a share in basis points (sum must == 10000)
fn shares_valid(shares: List<Int>) -> Bool {
  let total = list.foldl(shares, 0, fn(s, acc) { acc + s })
  total == 10000
}

/// Beneficiary's vested amount based on their share
fn beneficiary_amount(total_vested: Int, share_bps: Int) -> Int {
  total_vested * share_bps / 10000
}

/// All beneficiary amounts sum to at most total_vested (rounding down)
fn beneficiary_totals_le_vested(
  total_vested: Int,
  shares:       List<Int>,
) -> Bool {
  let paid = list.foldl(
    shares,
    0,
    fn(s, acc) { acc + beneficiary_amount(total_vested, s) },
  )
  paid <= total_vested
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_shares_sum_to_10000() {
  shares_valid([5000, 3000, 2000])
}

test prop_unequal_shares_invalid() {
  !shares_valid([5000, 3000])
}

test prop_beneficiary_full_share(
  total via fuzz.int_between(1, 100000),
) {
  beneficiary_amount(total, 10000) == total
}

test prop_beneficiary_totals_le_vested(
  total via fuzz.int_between(1, 100000),
) {
  beneficiary_totals_le_vested(total, [5000, 3000, 2000])
}
