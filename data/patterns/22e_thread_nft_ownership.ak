
/// Thread NFT must end up at an output controlled by the expected owner VKH
use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output, Transaction}
fn nft_at_owner(
  outputs:     List<Output>,
  auth_policy: PolicyId,
  auth_name:   ByteArray,
  owner_vkh:   ByteArray,
) -> Bool {
  let owner_addr = address.from_verification_key(owner_vkh)
  list.any(
    outputs,
    fn(o) {
      o.address == owner_addr
        && assets.quantity_of(o.value, auth_policy, auth_name) == 1
    },
  )
}

/// NFT must not be split across multiple outputs (quantity == 1 exactly once)
fn nft_unique(
  outputs:     List<Output>,
  auth_policy: PolicyId,
  auth_name:   ByteArray,
) -> Bool {
  let total = list.foldl(
    outputs,
    0,
    fn(o, acc) { acc + assets.quantity_of(o.value, auth_policy, auth_name) },
  )
  total == 1
}

// ── Validator ────────────────────────────────────────────────────────────────

pub type ThreadDatum {
  auth_policy: PolicyId,
  auth_name: ByteArray,
  owner_vkh: ByteArray,
}

pub type ThreadRedeemer {
  Transfer
  Burn
}

validator thread_nft_ownership {
  spend(
    datum: Option<ThreadDatum>,
    redeemer: ThreadRedeemer,
    _input: Data,
    self: Transaction,
  ) {
    expect Some(d) = datum
    when redeemer is {
      Transfer -> {
        let outputs = self.outputs
        nft_unique(outputs, d.auth_policy, d.auth_name)
          && nft_at_owner(outputs, d.auth_policy, d.auth_name, d.owner_vkh)
      }
      Burn ->
        nft_unique(self.outputs, d.auth_policy, d.auth_name) == False
    }
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_nft_at_correct_owner(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.verification_key_hash()),
) {
  let (policy, owner) = vals
  let val = assets.from_asset(policy, #"aa", 1)
  let out = Output { address: address.from_verification_key(owner), value: val, datum: NoDatum, reference_script: None }
  nft_at_owner([out], policy, #"aa", owner)
}

test prop_nft_at_wrong_owner_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.verification_key_hash()),
) {
  let (policy, owner) = vals
  let val = assets.from_asset(policy, #"aa", 1)
  let out = Output { address: address.from_verification_key(#"deadbeef"), value: val, datum: NoDatum, reference_script: None }
  !nft_at_owner([out], policy, #"aa", owner)
}

test prop_nft_unique_single_output(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let val = assets.from_asset(policy, name, 1)
  let out = Output { address: address.from_verification_key(#"aabb"), value: val, datum: NoDatum, reference_script: None }
  nft_unique([out], policy, name)
}

test prop_nft_not_unique_when_absent(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  !nft_unique([], policy, name)
}

// ── Negative (fail) property tests ───────────────────────────────────────────

/// nft_at_owner must fail when the output list is empty — no output can hold the NFT
test prop_fail_nft_at_owner_empty_outputs(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.verification_key_hash()),
) fail {
  let (policy, owner) = vals
  expect nft_at_owner([], policy, #"aa", owner)
}

/// nft_at_owner must fail when the NFT is present but sent to the wrong address
test prop_fail_nft_at_wrong_vkh(
  vals via fuzz.both(
    fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
    cfuzz.verification_key_hash(),
  ),
) fail {
  let ((policy, name), owner) = vals
  // NFT sits at a hardcoded address that never equals owner_vkh address
  let val = assets.from_asset(policy, name, 1)
  let out =
    Output {
      address: address.from_verification_key(#"deadbeef01"),
      value: val,
      datum: NoDatum,
      reference_script: None,
    }
  expect nft_at_owner([out], policy, name, owner)
}

/// nft_unique must fail when the output list is empty (total == 0, not 1)
test prop_fail_nft_unique_no_outputs(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  expect nft_unique([], policy, name)
}

/// nft_unique must fail when the NFT appears in two outputs (total == 2, not 1)
test prop_fail_nft_unique_duplicated(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  let val = assets.from_asset(policy, name, 1)
  let out1 =
    Output {
      address: address.from_verification_key(#"aabb"),
      value: val,
      datum: NoDatum,
      reference_script: None,
    }
  let out2 =
    Output {
      address: address.from_verification_key(#"ccdd"),
      value: val,
      datum: NoDatum,
      reference_script: None,
    }
  expect nft_unique([out1, out2], policy, name)
}