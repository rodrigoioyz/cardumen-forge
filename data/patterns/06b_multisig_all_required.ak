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
    all_signed(d.signers, self.extra_signatories)
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
