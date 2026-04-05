use aiken/collection/list
use aiken/fuzz

/// Milestone-based vesting: each milestone unlocks a fixed amount
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
  claim_amount:  Int,
  total:         Int,
  total_milestones: Int,
  completed:     Int,
) -> Bool {
  claim_amount > 0 && claim_amount <= total_unlocked(total, total_milestones, completed)
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
