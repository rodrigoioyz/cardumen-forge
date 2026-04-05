use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}

pub type BlacklistDatum {
  signers:   List<VerificationKeyHash>,
  threshold: Int,
  blacklist: List<VerificationKeyHash>,
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

/// None of the tx signatories may appear on the blacklist
fn none_blacklisted(
  signatories: List<VerificationKeyHash>,
  blacklist:   List<VerificationKeyHash>,
) -> Bool {
  list.all(signatories, fn(s) { !list.has(blacklist, s) })
}

validator multisig_blacklist {
  spend(
    datum: Option<BlacklistDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    none_blacklisted(self.extra_signatories, d.blacklist) && count_matching(
      d.signers,
      self.extra_signatories,
    ) >= d.threshold
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_blacklist_empty_ok(
  signatories via fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
) {
  none_blacklisted(signatories, [])
}

test prop_blacklist_self_fails(
  keys via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) {
  !none_blacklisted(keys, keys)
}

test prop_blacklist_empty_signatories(
  blacklist via fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
) {
  none_blacklisted([], blacklist)
}

test prop_count_bounded(
  vals via fuzz.both(
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
  ),
) {
  let (required, present) = vals
  count_matching(required, present) <= list.length(required)
}
