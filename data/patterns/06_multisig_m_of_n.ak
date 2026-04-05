use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}

pub type MultiSigDatum {
  signers:   List<VerificationKeyHash>,
  threshold: Int,
}

/// Count how many required signers are present in the tx signatories
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

validator multisig {
  spend(
    datum: Option<MultiSigDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let num_signers = list.length(d.signers)
    let threshold = d.threshold
    // Threshold must be a positive number and not exceed the signer list
    let threshold_valid = threshold > 0 && threshold <= num_signers
    // There must be at least one declared signer
    let has_signers = num_signers > 0
    // Count how many required signers actually signed this transaction
    let matched = count_matching(d.signers, self.extra_signatories)
    // The number of matched signers must meet or exceed the threshold
    let quorum_reached = matched >= threshold
    threshold_valid && has_signers && quorum_reached
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_count_matching_empty_required(
  present via fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
) {
  count_matching([], present) == 0
}

test prop_count_matching_empty_present(
  required via fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
) {
  count_matching(required, []) == 0
}

test prop_count_matching_non_negative(
  vals via fuzz.both(
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
  ),
) {
  let (required, present) = vals
  count_matching(required, present) >= 0
}

test prop_count_matching_bounded_by_required(
  vals via fuzz.both(
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
  ),
) {
  let (required, present) = vals
  count_matching(required, present) <= list.length(required)
}

test prop_count_matching_self_equals_length(
  keys via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) {
  count_matching(keys, keys) == list.length(keys)
}