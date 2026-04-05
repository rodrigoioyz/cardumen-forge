
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
    // min_bid must be positive
    let positive_min_bid = d.min_bid > 0
    // at least one output holds the NFT at all
    let nft_present_in_outputs =
      list.any(self.outputs, fn(o) { output_has_nft(o, d.nft_policy, d.nft_name) })
    // the full bid requirement (NFT + lovelace) is satisfied by some output
    let auction_satisfied =
      bid_accepted(self.outputs, d.nft_policy, d.nft_name, d.min_bid)
    // seller key is non-empty (basic datum sanity)
    let seller_set = d.seller != #""
    positive_min_bid && seller_set && nft_present_in_outputs && auction_satisfied
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// bid_accepted on an empty output list must always return False
test prop_bid_accepted_empty_outputs_fails(
  vals via fuzz.both(cfuzz.policy_id(), fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000000))),
) fail {
  let (policy, rest) = vals
  let (name, min_bid) = rest
  expect bid_accepted([], policy, name, min_bid)
}

/// output_has_nft must return False when the output carries no NFT at all
test prop_output_has_nft_no_nft_fails(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.from_lovelace(5000000),
      datum:            NoDatum,
      reference_script: None,
    }
  expect output_has_nft(output, policy, name)
}

/// valid_bid_output must return False when the output has the NFT but zero lovelace
/// (lovelace 0 < any positive min_bid)
test prop_valid_bid_output_no_lovelace_fails(
  vals via fuzz.both(cfuzz.policy_id(), fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000000))),
) fail {
  let (policy, rest) = vals
  let (name, min_bid) = rest
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.from_asset(policy, name, 1),
      datum:            NoDatum,
      reference_script: None,
    }
  expect valid_bid_output(output, policy, name, min_bid)
}

/// valid_bid_output must return False when the output has enough lovelace but no NFT
test prop_valid_bid_output_missing_nft_fails(
  vals via fuzz.both(cfuzz.policy_id(), fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000000))),
) fail {
  let (policy, rest) = vals
  let (name, min_bid) = rest
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.from_lovelace(min_bid),
      datum:            NoDatum,
      reference_script: None,
    }
  expect valid_bid_output(output, policy, name, min_bid)
}