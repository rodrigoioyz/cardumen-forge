
/// Each tranche is a node in a linked list of vesting schedules.
/// The beneficiary claims tranche N only after its unlock_slot.
use aiken/collection/list
use aiken/fuzz
use aiken/interval
use cardano/transaction.{OutputReference, Transaction}
pub type TrancheDatum {
  beneficiary:  ByteArray,
  tranche_idx:  Int,
  amount:       Int,
  unlock_slot:  Int,
  total_tranches: Int,
}

pub type VestingRedeemer {
  Claim
  Cancel
}

fn is_after(validity_range: interval.Interval, slot: Int) -> Bool {
  interval.is_entirely_after(validity_range, slot)
}

/// Tranche is claimable when the tx range is entirely past the unlock slot
fn tranche_unlocked(
  validity_range: interval.Interval,
  unlock_slot:    Int,
) -> Bool {
  is_after(validity_range, unlock_slot)
}

/// Amount claimable for tranche N out of total tranches
fn tranche_amount(total_amount: Int, tranche_idx: Int, total_tranches: Int) -> Int {
  total_amount / total_tranches + (
    if tranche_idx < total_amount % total_tranches {
      1
    } else {
      0
    }
  )
}

/// Total vested so far: sum of tranches 0..n (inclusive)
fn vested_through(
  total_amount:   Int,
  through_idx:    Int,
  total_tranches: Int,
) -> Int {
  list.foldl(
    list.range(0, through_idx),
    0,
    fn(i, acc) { acc + tranche_amount(total_amount, i, total_tranches) },
  )
}

validator vesting_tranche {
  spend(
    datum: Option<TrancheDatum>,
    redeemer: VestingRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      Claim ->
        tranche_unlocked(self.validity_range, d.unlock_slot)
      Cancel ->
        // Only claimable before unlock (issuer cancels unvested portion)
        !tranche_unlocked(self.validity_range, d.unlock_slot)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_tranche_unlocked_after(unlock_slot via fuzz.int_between(0, 999)) {
  tranche_unlocked(interval.after(1000), unlock_slot)
}

test prop_tranche_locked_before(unlock_slot via fuzz.int_between(1001, 2000)) {
  !tranche_unlocked(interval.before(1000), unlock_slot)
}

test prop_tranche_amount_sums_to_total(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(1, 10)),
) {
  let (total, n) = vals
  let sum =
    list.foldl(
      list.range(0, n - 1),
      0,
      fn(i, acc) { acc + tranche_amount(total, i, n) },
    )
  sum == total
}

test prop_vested_through_last_is_total(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(1, 10)),
) {
  let (total, n) = vals
  vested_through(total, n - 1, n) == total
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A tranche whose unlock_slot is in the FUTURE must NOT be unlocked.
/// interval.before(1000) covers slots up to 999, so any unlock_slot >= 1000
/// means the range is NOT entirely after the unlock_slot → tranche_unlocked = False.
test prop_tranche_not_unlocked_future_slot(
  unlock_slot via fuzz.int_between(1000, 9999),
) fail {
  expect tranche_unlocked(interval.before(1000), unlock_slot)
}

/// A tranche whose unlock_slot equals or exceeds the validity window end
/// is not yet claimable.  interval.after(5000) starts at 5001, so any
/// unlock_slot >= 5000 causes is_entirely_after to return False.
test prop_tranche_not_unlocked_at_boundary(
  unlock_slot via fuzz.int_between(5000, 10000),
) fail {
  expect tranche_unlocked(interval.after(5000), unlock_slot)
}

/// vested_through with through_idx = -1 (empty range) should give 0,
/// which is NOT equal to any positive total — prove the negation always fails.
test prop_vested_through_negative_idx_not_total(
  total via fuzz.int_between(1, 1000),
) fail {
  // list.range(0, -1) is empty, so vested_through returns 0, not total
  expect vested_through(total, -1, 1) == total
}

/// tranche_amount when tranche_idx equals total_tranches (out-of-range index)
/// gives the base quotient only (no remainder bonus), so for inputs where
/// total is not evenly divisible the result is strictly less than a fair share.
/// We verify the negation: it is NOT greater than the rounded-up per-tranche amount.
/// Concretely: with total=1, tranches=2, idx=2 → amount=0, which ≠ 1.
test prop_out_of_range_tranche_idx_gives_zero_for_unit_total() fail {
  // total=1, total_tranches=2, tranche_idx=2 → 1/2 + 0 = 0, not 1
  expect tranche_amount(1, 2, 2) == 1
}