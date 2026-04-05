
use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}
pub type AnySigDatum {
  signers: List<VerificationKeyHash>,
}

/// At least one required signer must be present (1-of-N)
fn any_signed(
  required: List<VerificationKeyHash>,
  present:  List<VerificationKeyHash>,
) -> Bool {
  list.any(required, fn(s) { list.has(present, s) })
}

validator multisig_any {
  spend(
    datum: Option<AnySigDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    // Datum must specify at least one allowed signer
    let has_signers = !list.is_empty(d.signers)
    // Transaction must carry at least one signatory
    let has_signatories = !list.is_empty(self.extra_signatories)
    // At least one of the required signers must have signed
    let authorised = any_signed(d.signers, self.extra_signatories)
    // All three conditions must hold
    has_signers && has_signatories && authorised
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_any_signed_empty_required_false(
  present via fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
) {
  !any_signed([], present)
}

test prop_any_signed_self(
  keys via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) {
  any_signed(keys, keys)
}

test prop_any_signed_empty_present_fails(
  required via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) {
  !any_signed(required, [])
}

test prop_any_signed_bounded(
  vals via fuzz.both(
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
  ),
) {
  let (required, present) = vals
  let result = any_signed(required, present)
  result == True || result == False
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// any_signed always returns False when `present` is empty and
/// `required` has at least one entry — expect True forces a runtime failure.
test prop_fail_any_signed_no_present(
  required via fuzz.list_between(cfuzz.verification_key_hash(), 1, 6),
) fail {
  expect any_signed(required, [])
}

/// any_signed always returns False when `required` is empty — no element
/// of the empty list can ever be found in `present`.
test prop_fail_any_signed_no_required(
  present via fuzz.list_between(cfuzz.verification_key_hash(), 0, 6),
) fail {
  expect any_signed([], present)
}

/// any_signed returns False when both lists are empty.
test fail_any_signed_both_empty() fail {
  expect any_signed([], [])
}

/// any_signed returns False when the single required key is a fixed
/// byte-string that cannot appear in a list of distinct fuzzed keys
/// (the fuzzed keys are virtually never equal to the hardcoded value).
/// We guarantee failure by using a hardcoded required key and passing
/// an empty present list, making the result definitively False.
test prop_fail_any_signed_hardcoded_key_no_present(
  _dummy via fuzz.int_between(0, 0),
) fail {
  let hardcoded_required: List<VerificationKeyHash> =
    [#"deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef01"]
  expect any_signed(hardcoded_required, [])
}