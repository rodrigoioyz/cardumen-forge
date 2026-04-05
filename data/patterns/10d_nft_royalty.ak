
use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/assets.{AssetName, PolicyId, lovelace_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output, OutputReference, Transaction}
pub type RoyaltyDatum {
  seller:         ByteArray,
  creator:        ByteArray,
  nft_policy:     PolicyId,
  nft_name:       AssetName,
  price:          Int,
  royalty_pct:    Int,
}

fn output_has_nft(output: Output, policy: PolicyId, name: AssetName) -> Bool {
  assets.quantity_of(output.value, policy, name) == 1
}

fn lovelace_to(outputs: List<Output>, key: ByteArray) -> Int {
  let addr = address.from_verification_key(key)
  list.foldl(
    list.filter(outputs, fn(o) { o.address == addr }),
    0,
    fn(o, acc) { acc + lovelace_of(o.value) },
  )
}

/// Required royalty amount
fn royalty_amount(price: Int, royalty_pct: Int) -> Int {
  price * royalty_pct / 100
}

/// Seller gets (price - royalty), creator gets royalty
fn royalty_paid(
  outputs:     List<Output>,
  seller:      ByteArray,
  creator:     ByteArray,
  price:       Int,
  royalty_pct: Int,
) -> Bool {
  let royalty  = royalty_amount(price, royalty_pct)
  let to_seller = price - royalty
  lovelace_to(outputs, creator) >= royalty && lovelace_to(outputs, seller) >= to_seller
}

validator nft_royalty {
  spend(
    datum: Option<RoyaltyDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    royalty_paid(
      self.outputs,
      d.seller,
      d.creator,
      d.price,
      d.royalty_pct,
    )
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_royalty_amount_zero_pct(price via fuzz.int_between(1, 1000000)) {
  royalty_amount(price, 0) == 0
}

test prop_royalty_amount_100_pct(price via fuzz.int_between(1, 1000000)) {
  royalty_amount(price, 100) == price
}

test prop_royalty_amount_less_than_price(
  vals via fuzz.both(fuzz.int_between(100, 1000000), fuzz.int_between(1, 99)),
) {
  let (price, pct) = vals
  royalty_amount(price, pct) < price
}

test prop_output_has_nft_correct(
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
  output_has_nft(output, policy, name)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// output_has_nft returns False when the output holds 0 of the asset
test prop_output_missing_nft_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.zero,
      datum:            NoDatum,
      reference_script: None,
    }
  expect output_has_nft(output, policy, name)
}

/// royalty_paid returns False when no outputs are present (no payments at all)
/// and price > 0, royalty_pct >= 0
test prop_no_outputs_royalty_rejected(
  vals via fuzz.both(fuzz.int_between(1, 1000000), fuzz.int_between(0, 100)),
) fail {
  let (price, pct) = vals
  expect royalty_paid([], #"aabb", #"ccdd", price, pct)
}

/// royalty_paid returns False when seller is paid but creator receives nothing
/// and royalty_pct > 0, ensuring royalty > 0
test prop_creator_unpaid_royalty_rejected(
  vals via fuzz.both(fuzz.int_between(100, 1000000), fuzz.int_between(1, 50)),
) fail {
  let (price, pct) = vals
  let seller_key = #"aabb"
  let creator_key = #"ccdd"
  // Pay seller the full price but nothing to creator
  let seller_output =
    Output {
      address:          address.from_verification_key(seller_key),
      value:            assets.from_lovelace(price),
      datum:            NoDatum,
      reference_script: None,
    }
  expect royalty_paid([seller_output], seller_key, creator_key, price, pct)
}

/// royalty_paid returns False when creator is paid but seller receives nothing
/// price >= 2 and royalty_pct between 1 and 99 so to_seller > 0
test prop_seller_unpaid_royalty_rejected(
  vals via fuzz.both(fuzz.int_between(100, 1000000), fuzz.int_between(1, 99)),
) fail {
  let (price, pct) = vals
  let seller_key = #"aabb"
  let creator_key = #"ccdd"
  let royalty = royalty_amount(price, pct)
  // Pay creator their royalty but nothing to seller
  let creator_output =
    Output {
      address:          address.from_verification_key(creator_key),
      value:            assets.from_lovelace(royalty),
      datum:            NoDatum,
      reference_script: None,
    }
  expect royalty_paid([creator_output], seller_key, creator_key, price, pct)
}