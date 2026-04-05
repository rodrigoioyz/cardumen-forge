
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A single signer that IS on the blacklist must always be rejected.
test prop_single_signer_on_blacklist_rejected(
  key via cfuzz.verification_key_hash(),
) fail {
  expect none_blacklisted([key], [key])
}

/// When every signatory appears on the blacklist the check must fail,
/// regardless of how many signatories there are (at least one).
test prop_all_signatories_blacklisted_rejected(
  keys via fuzz.list_between(cfuzz.verification_key_hash(), 1, 6),
) fail {
  expect none_blacklisted(keys, keys)
}

/// count_matching can never exceed the number of required keys,
/// so requiring more matches than there are required keys is impossible —
/// i.e. count_matching always returns < threshold when threshold > |required|.
/// We encode this as: count_matching(required, required) >= threshold
/// must be False when threshold > list.length(required).
test prop_count_below_inflated_threshold(
  keys via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) fail {
  // threshold is length+1, so count can never reach it
  let threshold = list.length(keys) + 1
  expect count_matching(keys, keys) >= threshold
}

/// none_blacklisted must return False when even one element of
/// signatories appears in a larger blacklist.
test prop_signatory_in_large_blacklist_rejected(
  vals via fuzz.both(
    cfuzz.verification_key_hash(),
    fuzz.list_between(cfuzz.verification_key_hash(), 0, 4),
  ),
) fail {
  let (key, extras) = vals
  // blacklist = [key, ...extras], signatories = [key]
  expect none_blacklisted([key], [key, ..extras])
}