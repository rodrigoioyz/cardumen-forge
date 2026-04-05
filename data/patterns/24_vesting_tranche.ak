use aiken/collection/list
use aiken/fuzz
use aiken/interval
use cardano/transaction.{OutputReference, Transaction}

/// Each tranche is a node in a linked list of vesting schedules.
/// The beneficiary claims tranche N only after its unlock_slot.
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
