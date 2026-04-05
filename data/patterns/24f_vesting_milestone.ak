
/// Milestone-based vesting: each milestone unlocks a fixed amount
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{lovelace_of}
use cardano/transaction.{Transaction}
fn milestone_amount(total: Int, milestone_count: Int) -> Int {
  total / milestone_count
}

/// Total unlocked after completing n_completed milestones
fn total_unlocked(total: Int, milestone_count: Int, n_completed: Int) -> Int {
  list.foldl(
    list.range(0, n_completed - 1),
    0,
    fn(_, acc) { acc + milestone_amount(total, milestone_count) },
  )
}

/// Cannot claim more than what milestones have unlocked
fn claim_within_unlocked(
  claim_amount: Int,
  total: Int,
  total_milestones: Int,
  completed: Int,
) -> Bool {
  claim_amount > 0 && claim_amount <= total_unlocked(total, total_milestones, completed)
}

// ── Datum / Redeemer ─────────────────────────────────────────────────────────

pub type VestingDatum {
  total_amount: Int,
  total_milestones: Int,
  completed_milestones: Int,
  beneficiary: ByteArray,
}

pub type VestingRedeemer {
  claim_amount: Int,
}

// ── Validator ────────────────────────────────────────────────────────────────

validator milestone_vesting {
  spend(
    datum: Option<VestingDatum>,
    redeemer: VestingRedeemer,
    _output_ref: Data,
    self: Transaction,
  ) {
    expect Some(d) = datum
    let VestingRedeemer { claim_amount } = redeemer
    let signed_by_beneficiary =
      list.any(
        self.extra_signatories,
        fn(key) { key == d.beneficiary },
      )
    let valid_claim =
      claim_within_unlocked(
        claim_amount,
        d.total_amount,
        d.total_milestones,
        d.completed_milestones,
      )
    let outputs_lovelace =
      list.foldl(
        self.outputs,
        0,
        fn(o, acc) { acc + lovelace_of(o.value) },
      )
    let sufficient_remainder =
      outputs_lovelace >= d.total_amount - claim_amount
    signed_by_beneficiary && valid_claim && sufficient_remainder
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_milestone_amount_divides_evenly(
  vals via fuzz.both(fuzz.int_between(4, 1000), fuzz.int_between(1, 4)),
) {
  let (total, n) = vals
  milestone_amount(total * n, n) == total
}

test prop_no_completed_milestones_zero_unlocked(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 5)),
) {
  let (total, n) = vals
  total_unlocked(total, n, 0) == 0
}

test prop_all_milestones_unlocks_most(
  vals via fuzz.both(fuzz.int_between(10, 1000), fuzz.int_between(1, 5)),
) {
  let (total, n) = vals
  total_unlocked(total, n, n) >= total - n
}

test prop_claim_within_unlocked_valid(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(1, 3)),
) {
  let (total, completed) = vals
  let unlocked = total_unlocked(total, 4, completed)
  unlocked == 0 || claim_within_unlocked(1, total, 4, completed)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Zero claim amount is always invalid regardless of how much is unlocked
test prop_zero_claim_rejected(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(1, 5)),
) fail {
  let (total, completed) = vals
  // claim_amount = 0 fails the `claim_amount > 0` guard
  expect claim_within_unlocked(0, total, 4, completed)
}

/// Negative claim amount is always invalid
test prop_negative_claim_rejected(
  vals via fuzz.both(fuzz.int_between(-1000, -1), fuzz.int_between(100, 1000)),
) fail {
  let (claim, total) = vals
  // negative claim_amount fails the `claim_amount > 0` guard
  expect claim_within_unlocked(claim, total, 4, 4)
}

/// Claiming more than the unlocked amount must be rejected
/// With 0 completed milestones, unlocked = 0, so any positive claim > 0 fails
test prop_overclaim_with_no_milestones_completed_rejected(
  claim via fuzz.int_between(1, 10000),
) fail {
  // total_unlocked(1000, 4, 0) == 0, so claim > 0 always exceeds unlocked
  expect claim_within_unlocked(claim, 1000, 4, 0)
}

/// Claiming more than the total unlocked across all milestones must be rejected
/// total_unlocked(100, 4, 4) = 4 * (100/4) = 100, so claim > 100 always fails
test prop_overclaim_exceeds_total_unlocked_rejected(
  claim via fuzz.int_between(101, 10000),
) fail {
  // total_unlocked(100, 4, 4) == 100; claim >= 101 always exceeds it
  expect claim_within_unlocked(claim, 100, 4, 4)
}