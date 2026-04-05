
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
    // Must have at least one required signer defined
    let has_signers = list.length(d.signers) > 0
    // Count how many required signers are present in extra_signatories
    let matching = count_matching(d.signers, self.extra_signatories)
    // Strict majority quorum must be reached
    let majority = quorum_reached(d.signers, self.extra_signatories)
    // At least one signer must actually be present
    let at_least_one = matching > 0
    has_signers && at_least_one && majority
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

// ── Negative (fail) tests ────────────────────────────────────────────────────

// quorum_reached with empty required list always returns False
// because 0 * 2 > 0 is False
test prop_quorum_empty_required_rejected(
  present via fuzz.list_between(cfuzz.verification_key_hash(), 0, 8),
) fail {
  expect quorum_reached([], present)
}

// quorum_reached with no present signers always returns False
// because count_matching(required, []) = 0, and 0 * 2 > n is False for n >= 1
test prop_quorum_no_present_rejected(
  required via fuzz.list_between(cfuzz.verification_key_hash(), 1, 8),
) fail {
  expect quorum_reached(required, [])
}

// count_matching against an empty present list always returns 0
// We expect it to be > 0, which is always False — so this always fails
test prop_count_matching_empty_present_is_zero(
  required via fuzz.list_between(cfuzz.verification_key_hash(), 1, 8),
) fail {
  expect count_matching(required, []) > 0
}

// A single required signer that is NOT in the present list means quorum fails.
// We use two distinct fixed-length bytearrays: required=[key1], present=[key2]
// where key1 != key2 is guaranteed by using hardcoded distinct values.
test prop_quorum_single_wrong_signer_rejected() fail {
  let required = [#"aabbccdd00112233445566778899aabbccdd001122334455667788"]
  let present  = [#"0011223344556677889900aabbccdd0011223344556677889900aa"]
  expect quorum_reached(required, present)
}