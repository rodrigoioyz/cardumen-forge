use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/assets.{AssetName, PolicyId, lovelace_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output, OutputReference, Transaction}

pub type PreserveDatum {
  owner:      ByteArray,
  nft_policy: PolicyId,
  nft_name:   AssetName,
  loan_amount: Int,
}

pub type PreserveRedeemer {
  Use
  Reclaim
}

fn output_has_nft(output: Output, policy: PolicyId, name: AssetName) -> Bool {
  assets.quantity_of(output.value, policy, name) == 1
}

/// NFT must be preserved in at least one output (still circulating)
fn nft_preserved(
  outputs: List<Output>,
  policy:  PolicyId,
  name:    AssetName,
) -> Bool {
  list.any(outputs, fn(o) { output_has_nft(o, policy, name) })
}

fn owner_paid(outputs: List<Output>, owner_key: ByteArray, amount: Int) -> Bool {
  let addr = address.from_verification_key(owner_key)
  let paid =
    list.foldl(
      list.filter(outputs, fn(o) { o.address == addr }),
      0,
      fn(o, acc) { acc + lovelace_of(o.value) },
    )
  paid >= amount
}

validator nft_preserve {
  spend(
    datum: Option<PreserveDatum>,
    redeemer: PreserveRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      Use ->
        // NFT must stay in circulation and owner gets paid
        nft_preserved(self.outputs, d.nft_policy, d.nft_name) && owner_paid(
          self.outputs,
          d.owner,
          d.loan_amount,
        )
      Reclaim ->
        // Owner reclaims NFT — must sign
        list.has(self.extra_signatories, d.owner)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_nft_preserved_in_outputs(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.from_asset(policy, name, 1),
      datum:            NoDatum,
      reference_script: None,
    }
  nft_preserved([output], policy, name)
}

test prop_nft_not_preserved_empty(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  !nft_preserved([], policy, name)
}

test prop_nft_not_preserved_wrong_qty(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.from_lovelace(2000000),
      datum:            NoDatum,
      reference_script: None,
    }
  !nft_preserved([output], policy, name)
}

test prop_output_has_nft_qty_one(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let output =
    Output {
      address:          address.from_verification_key(#"ccdd"),
      value:            assets.from_asset(policy, name, 1),
      datum:            NoDatum,
      reference_script: None,
    }
  output_has_nft(output, policy, name)
}
