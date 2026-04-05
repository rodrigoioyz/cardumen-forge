use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/assets.{AssetName, PolicyId, lovelace_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output, OutputReference, Transaction}

pub type AuctionDatum {
  seller:     ByteArray,
  nft_policy: PolicyId,
  nft_name:   AssetName,
  min_bid:    Int,
}

fn output_has_nft(output: Output, policy: PolicyId, name: AssetName) -> Bool {
  assets.quantity_of(output.value, policy, name) == 1
}

/// Winning bid output must contain the NFT and at least min_bid lovelace
fn valid_bid_output(
  output:   Output,
  policy:   PolicyId,
  name:     AssetName,
  min_bid:  Int,
) -> Bool {
  output_has_nft(output, policy, name) && lovelace_of(output.value) >= min_bid
}

/// At least one output meets the bid requirements
fn bid_accepted(
  outputs:  List<Output>,
  policy:   PolicyId,
  name:     AssetName,
  min_bid:  Int,
) -> Bool {
  list.any(outputs, fn(o) { valid_bid_output(o, policy, name, min_bid) })
}

validator nft_auction_bid {
  spend(
    datum: Option<AuctionDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    bid_accepted(self.outputs, d.nft_policy, d.nft_name, d.min_bid)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_valid_bid_nft_and_lovelace(
  vals via fuzz.both(cfuzz.policy_id(), fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000000))),
) {
  let (policy, rest) = vals
  let (name, min_bid) = rest
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.merge(assets.from_asset(policy, name, 1), assets.from_lovelace(min_bid)),
      datum:            NoDatum,
      reference_script: None,
    }
  valid_bid_output(output, policy, name, min_bid)
}

test prop_bid_missing_nft_fails(
  vals via fuzz.both(cfuzz.policy_id(), fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000000))),
) {
  let (policy, rest) = vals
  let (name, min_bid) = rest
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.from_lovelace(min_bid),
      datum:            NoDatum,
      reference_script: None,
    }
  !valid_bid_output(output, policy, name, min_bid)
}

test prop_bid_below_min_fails(
  vals via fuzz.both(cfuzz.policy_id(), fuzz.both(cfuzz.asset_name(), fuzz.int_between(2, 1000000))),
) {
  let (policy, rest) = vals
  let (name, min_bid) = rest
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.merge(assets.from_asset(policy, name, 1), assets.from_lovelace(min_bid - 1)),
      datum:            NoDatum,
      reference_script: None,
    }
  !valid_bid_output(output, policy, name, min_bid)
}

test prop_output_nft_zero_fails(
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
  !output_has_nft(output, policy, name)
}
