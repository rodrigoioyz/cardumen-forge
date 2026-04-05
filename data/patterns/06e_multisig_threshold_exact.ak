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
    exact_threshold(d.signers, self.extra_signatories, d.threshold)
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
