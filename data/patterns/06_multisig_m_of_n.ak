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
    count_matching(d.signers, self.extra_signatories) >= d.threshold
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
