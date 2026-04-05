
/// The continuing output must carry at least min_lovelace in addition to the NFT
use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output}
fn value_locked_ok(
  output:       Output,
  auth_policy:  PolicyId,
  auth_name:    ByteArray,
  min_lovelace: Int,
) -> Bool {
  assets.quantity_of(output.value, auth_policy, auth_name) == 1
    && assets.lovelace_of(output.value) >= min_lovelace
}

/// Find the first output that satisfies value_locked_ok
fn find_locked_output(
  outputs:      List<Output>,
  auth_policy:  PolicyId,
  auth_name:    ByteArray,
  min_lovelace: Int,
) -> Option<Output> {
  list.find(
    outputs,
    fn(o) { value_locked_ok(o, auth_policy, auth_name, min_lovelace) },
  )
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_output_with_nft_and_lovelace_found(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let nft_val = assets.from_asset(policy, name, 1)
  let val     = assets.merge(nft_val, assets.from_lovelace(2_000_000))
  let out     = Output { address: address.from_verification_key(#"aabb"), value: val, datum: NoDatum, reference_script: None }
  value_locked_ok(out, policy, name, 2_000_000)
}

test prop_output_missing_nft_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let val = assets.from_lovelace(5_000_000)
  let out = Output { address: address.from_verification_key(#"aabb"), value: val, datum: NoDatum, reference_script: None }
  !value_locked_ok(out, policy, name, 2_000_000)
}

test prop_output_insufficient_lovelace_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let nft_val = assets.from_asset(policy, name, 1)
  let val     = assets.merge(nft_val, assets.from_lovelace(1_000_000))
  let out     = Output { address: address.from_verification_key(#"aabb"), value: val, datum: NoDatum, reference_script: None }
  !value_locked_ok(out, policy, name, 2_000_000)
}

test prop_find_returns_none_on_empty() {
  find_locked_output([], #"aabb", #"ccdd", 1_000_000) == None
}

// ── Datum / Redeemer types ────────────────────────────────────────────────────

pub type ThreadDatum {
  auth_policy: PolicyId,
  auth_name: ByteArray,
  min_lovelace: Int,
}

pub type ThreadRedeemer {
  Continue
  Close
}

// ── Validator ─────────────────────────────────────────────────────────────────

validator thread_nft_value_lock {
  spend(
    datum: Option<ThreadDatum>,
    redeemer: ThreadRedeemer,
    _own_ref: Data,
    self: transaction.Transaction,
  ) {
    expect Some(d) = datum
    when redeemer is {
      Close -> False
      Continue -> {
        let result =
          find_locked_output(
            self.outputs,
            d.auth_policy,
            d.auth_name,
            d.min_lovelace,
          )
        when result is {
          Some(out) -> value_locked_ok(out, d.auth_policy, d.auth_name, d.min_lovelace)
          None -> False
        }
      }
    }
  }
}

// ── Negative (fail) property tests ───────────────────────────────────────────

/// An output with no NFT and no lovelace must always be rejected
test prop_fail_empty_value_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  let out = Output {
    address: address.from_verification_key(#"aabb"),
    value: assets.zero,
    datum: NoDatum,
    reference_script: None,
  }
  expect value_locked_ok(out, policy, name, 1)
}

/// An output with the NFT but lovelace strictly below min_lovelace must be rejected.
/// We use lovelace=0 and min_lovelace=1 to guarantee failure.
test prop_fail_nft_present_but_zero_lovelace(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  // assets.from_asset alone carries no lovelace entry, so lovelace_of == 0
  let val = assets.from_asset(policy, name, 1)
  let out = Output {
    address: address.from_verification_key(#"aabb"),
    value: val,
    datum: NoDatum,
    reference_script: None,
  }
  expect value_locked_ok(out, policy, name, 1)
}

/// find_locked_output on an empty list must always return None,
/// so wrapping with expect Some(_) must always fail.
test prop_fail_find_locked_empty_list(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  expect Some(_) = find_locked_output([], policy, name, 1_000_000)
}

/// An output carrying only lovelace (no NFT) must be rejected even with
/// a very high lovelace amount.
test prop_fail_only_lovelace_no_nft(
  vals via fuzz.both(
    fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
    fuzz.int_between(1, 100_000_000),
  ),
) fail {
  let ((policy, name), lovelace) = vals
  let val = assets.from_lovelace(lovelace)
  let out = Output {
    address: address.from_verification_key(#"aabb"),
    value: val,
    datum: NoDatum,
    reference_script: None,
  }
  expect value_locked_ok(out, policy, name, lovelace)
}