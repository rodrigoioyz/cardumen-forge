
/// Each beneficiary has a share in basis points (sum must == 10000)
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{lovelace_of}
use cardano/transaction.{Transaction, InlineDatum}
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

// ── Datum / Redeemer types ────────────────────────────────────────────────────

pub type VestingDatum {
  beneficiaries: List<ByteArray>,
  shares: List<Int>,
  unlock_after: Int,
}

pub type VestingRedeemer {
  Claim
}

// ── Validator ─────────────────────────────────────────────────────────────────

validator multi_beneficiary_vesting {
  spend(
    datum: Option<VestingDatum>,
    _redeemer: VestingRedeemer,
    _own_ref: Data,
    self: Transaction,
  ) {
    expect Some(d) = datum
    let total_vested =
      list.foldl(
        self.inputs,
        0,
        fn(inp, acc) { acc + lovelace_of(inp.output.value) },
      )
    expect shares_valid(d.shares)
    expect beneficiary_totals_le_vested(total_vested, d.shares)
    let n_beneficiaries = list.length(d.beneficiaries)
    let n_shares = list.length(d.shares)
    n_beneficiaries == n_shares && n_beneficiaries > 0
  }

  else(_) {
    fail
  }
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

// ── Negative / fail tests ─────────────────────────────────────────────────────

/// Empty list of shares sums to 0, not 10000 — always invalid
test prop_empty_shares_invalid() fail {
  expect shares_valid([])
}

/// A single share that is not exactly 10000 is always invalid
/// Use range 1..9999 to guarantee the sum is strictly less than 10000
test prop_single_share_below_10000_invalid(
  s via fuzz.int_between(1, 9999),
) fail {
  expect shares_valid([s])
}

/// Two shares that together overshoot 10000 are always invalid.
/// Both drawn from 5001..9999, so their sum is at least 10002.
test prop_overshoot_shares_invalid(
  vals via fuzz.both(fuzz.int_between(5001, 9999), fuzz.int_between(5001, 9999)),
) fail {
  let (a, b) = vals
  expect shares_valid([a, b])
}

/// A list of shares that sums to exactly 9999 is always invalid.
/// We use [5000, 4999] which sums to 9999, never 10000.
test prop_shares_sum_9999_invalid() fail {
  expect shares_valid([5000, 4999])
}