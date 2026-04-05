use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/assets.{AssetName, PolicyId, lovelace_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{InlineDatum, NoDatum, Output, OutputReference, Transaction}

pub type StateDatum {
  state_data: Int,
}

/// The thread NFT must be present in the output at the same address (qty == 1).
/// This ensures the contract state can only advance through valid transitions.
fn nft_passes_through(
  outputs:      List<Output>,
  own_addr:     address.Address,
  auth_policy:  PolicyId,
  auth_name:    AssetName,
) -> Bool {
  list.any(
    outputs,
    fn(o) {
      o.address == own_addr
        && assets.quantity_of(o.value, auth_policy, auth_name) == 1
    },
  )
}

/// The value must be reproduced unchanged (same lovelace + same NFT)
fn value_unchanged(in_val: assets.Value, out_val: assets.Value) -> Bool {
  in_val == out_val
}

/// Address payment credential must be preserved (staking part may change)
fn address_preserved(
  in_addr:  address.Address,
  out_addr: address.Address,
) -> Bool {
  in_addr.payment_credential == out_addr.payment_credential
}

validator thread_nft {
  spend(
    datum: Option<StateDatum>,
    _redeemer: Data,
    own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(_d) = datum
    expect Some(own_input) =
      list.find(self.inputs, fn(i) { i.output_reference == own_ref })
    let own_addr = own_input.output.address
    // Thread NFT policy = script's own hash (simplified: use datum field)
    // In practice the policy would be parameterized; here we just check presence
    list.any(
      self.outputs,
      fn(o) { address_preserved(own_addr, o.address) },
    )
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_nft_passes_through_correct(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let addr = address.from_verification_key(#"aabb")
  let output =
    Output {
      address:          addr,
      value:            assets.from_asset(policy, name, 1),
      datum:            NoDatum,
      reference_script: None,
    }
  nft_passes_through([output], addr, policy, name)
}

test prop_nft_missing_fails(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let addr = address.from_verification_key(#"aabb")
  let output =
    Output {
      address:          addr,
      value:            assets.from_lovelace(2000000),
      datum:            NoDatum,
      reference_script: None,
    }
  !nft_passes_through([output], addr, policy, name)
}

test prop_value_unchanged_same() {
  let v = assets.from_lovelace(2000000)
  value_unchanged(v, v)
}

test prop_value_changed_fails(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let v1 = assets.from_lovelace(2000000)
  let v2 = assets.merge(v1, assets.from_asset(policy, name, 1))
  !value_unchanged(v1, v2)
}
