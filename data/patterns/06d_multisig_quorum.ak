use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}

pub type QuorumDatum {
  signers: List<VerificationKeyHash>,
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

/// Strict majority: more than half of required signers must sign
fn quorum_reached(
  required: List<VerificationKeyHash>,
  present:  List<VerificationKeyHash>,
) -> Bool {
  count_matching(required, present) * 2 > list.length(required)
}

validator multisig_quorum {
  spend(
    datum: Option<QuorumDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    quorum_reached(d.signers, self.extra_signatories)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_quorum_empty_fails(
  present via fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
) {
  !quorum_reached([], present)
}

test prop_quorum_self_reaches(
  keys via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) {
  quorum_reached(keys, keys)
}

test prop_quorum_none_present_fails(
  required via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) {
  !quorum_reached(required, [])
}

test prop_quorum_count_bounded(
  vals via fuzz.both(
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
  ),
) {
  let (required, present) = vals
  count_matching(required, present) <= list.length(required)
}
