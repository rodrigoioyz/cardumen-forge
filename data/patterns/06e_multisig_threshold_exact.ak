
use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}
pub type ExactThresholdDatum {
  signers:   List<VerificationKeyHash>,
  threshold: Int,
}

fn count_matching(
  required: List<VerificationKeyHash>,
  present:  List<VerificationKeyHash>,
) -> Int {
  list.foldl(
    required,
    0,
    fn(req, acc) {
      if list.has(present, req) {
        acc + 1
      } else {
        acc
      }
    },
  )
}

/// Exactly `threshold` signers must sign — no more, no less
fn exact_threshold(
  required:  List<VerificationKeyHash>,
  present:   List<VerificationKeyHash>,
  threshold: Int,
) -> Bool {
  count_matching(required, present) == threshold
}

validator multisig_exact {
  spend(
    datum: Option<ExactThresholdDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    // Datum must specify a positive threshold
    let threshold_valid = d.threshold > 0
    // Threshold must not exceed the number of required signers
    let threshold_in_range = d.threshold <= list.length(d.signers)
    // There must be at least one declared signer
    let has_signers = list.length(d.signers) > 0
    // Count how many required signers have actually signed
    let matched = count_matching(d.signers, self.extra_signatories)
    // Exactly `threshold` of the required signers must be present
    let exactly_met = matched == d.threshold
    // Combine all conditions
    threshold_valid && threshold_in_range && has_signers && exactly_met && exact_threshold(d.signers, self.extra_signatories, d.threshold)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_exact_empty_zero(
  present via fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
) {
  exact_threshold([], present, 0)
}

test prop_exact_self_equals_length(
  keys via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) {
  exact_threshold(keys, keys, list.length(keys))
}

test prop_exact_none_present_zero(
  required via fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
) {
  exact_threshold(required, [], 0)
}

test prop_exact_count_bounded(
  vals via fuzz.both(
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
  ),
) {
  let (required, present) = vals
  count_matching(required, present) <= list.length(required)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// A non-empty required list with no present signers can never match threshold >= 1
test prop_exact_no_signers_nonzero_threshold_fails(
  vals via fuzz.both(
    fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
    fuzz.int_between(1, 5),
  ),
) fail {
  let (required, threshold) = vals
  // count_matching(required, []) == 0, which never equals threshold >= 1
  expect exact_threshold(required, [], threshold)
}

// Threshold larger than the number of required signers can never be satisfied
// even when all required signers are present (count <= length(required) < threshold)
test prop_exact_threshold_exceeds_required_fails(
  vals via fuzz.both(
    fuzz.list_between(cfuzz.verification_key_hash(), 1, 4),
    fuzz.int_between(5, 10),
  ),
) fail {
  let (required, threshold) = vals
  // max count_matching == list.length(required) <= 4 < 5 <= threshold
  expect exact_threshold(required, required, threshold)
}

// Threshold of zero with a non-empty required list that is fully signed fails
// because count_matching >= 1 != 0
test prop_exact_zero_threshold_with_matching_fails(
  keys via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) fail {
  // count_matching(keys, keys) == length(keys) >= 1, never == 0
  expect exact_threshold(keys, keys, 0)
}

// count_matching on a non-empty required list against itself is always
// list.length(required), so it never equals a strictly smaller positive value
test prop_exact_partial_threshold_all_present_fails(
  vals via fuzz.both(
    fuzz.list_between(cfuzz.verification_key_hash(), 2, 5),
    fuzz.int_between(1, 1),
  ),
) fail {
  let (required, _) = vals
  let full_count = list.length(required)
  // full_count >= 2, so full_count != full_count - 1
  expect exact_threshold(required, required, full_count - 1)
}