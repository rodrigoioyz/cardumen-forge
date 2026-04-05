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
    any_signed(d.signers, self.extra_signatories)
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
