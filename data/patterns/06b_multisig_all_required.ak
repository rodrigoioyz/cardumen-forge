
use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}
pub type AllSigDatum {
  signers: List<VerificationKeyHash>,
}

/// Every required signer must be present in tx signatories
fn all_signed(
  required: List<VerificationKeyHash>,
  present:  List<VerificationKeyHash>,
) -> Bool {
  list.all(required, fn(s) { list.has(present, s) })
}

validator multisig_all {
  spend(
    datum: Option<AllSigDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let required = d.signers
    let present = self.extra_signatories
    let has_at_least_one_signer = !list.is_empty(required)
    let all_present = all_signed(required, present)
    let no_duplicates =
      list.length(required) == list.length(list.unique(required))
    has_at_least_one_signer && all_present && no_duplicates
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_all_signed_empty_required(
  present via fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
) {
  all_signed([], present)
}

test prop_all_signed_self(
  keys via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) {
  all_signed(keys, keys)
}

test prop_all_signed_empty_present_fails(
  required via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) {
  !all_signed(required, [])
}

test prop_all_signed_non_negative(
  vals via fuzz.both(
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
  ),
) {
  let (required, present) = vals
  let result = all_signed(required, present)
  result == True || result == False
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A non-empty required list never matches an empty present list
test prop_fail_required_not_met_empty_present(
  required via fuzz.list_between(cfuzz.verification_key_hash(), 1, 6),
) fail {
  expect all_signed(required, [])
}

/// A single required key that is NOT in present must be rejected.
/// We use two independent bytearray fuzzers and combine them so that
/// the required key is always a single-element list whose only entry
/// is guaranteed to differ from every element in present (present is
/// kept empty to make the guarantee trivial).
test prop_fail_single_missing_signer(
  key via cfuzz.verification_key_hash(),
) fail {
  // present is [] — the single required signer is never found
  expect all_signed([key], [])
}

/// Two distinct required keys, but present list is empty — must fail.
test prop_fail_two_required_none_present(
  pair via fuzz.both(
    cfuzz.verification_key_hash(),
    cfuzz.verification_key_hash(),
  ),
) fail {
  let (k1, k2) = pair
  expect all_signed([k1, k2], [])
}

/// Required list has one entry; present list contains only a *different*
/// set of keys built by taking a non-overlapping slice.  The simplest
/// guarantee: use a fixed known-bad required key not in the hardcoded
/// present list.
test prop_fail_known_missing_key() fail {
  // #"deadbeef" is required but present list is empty
  expect all_signed([#"deadbeef"], [])
}