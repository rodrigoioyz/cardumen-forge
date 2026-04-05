use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/assets.{AssetName, PolicyId, lovelace_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output, OutputReference, Transaction}

pub type SaleDatum {
  seller:    ByteArray,
  nft_policy: PolicyId,
  nft_name:  AssetName,
  price:     Int,
}

fn output_has_nft(output: Output, policy: PolicyId, name: AssetName) -> Bool {
  assets.quantity_of(output.value, policy, name) == 1
}

/// Seller must receive at least `price` lovelace
fn seller_paid(outputs: List<Output>, seller_key: ByteArray, price: Int) -> Bool {
  let addr = address.from_verification_key(seller_key)
  let paid =
    list.foldl(
      list.filter(outputs, fn(o) { o.address == addr }),
      0,
      fn(o, acc) { acc + lovelace_of(o.value) },
    )
  paid >= price
}

validator nft_buy_now {
  spend(
    datum: Option<SaleDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    seller_paid(self.outputs, d.seller, d.price)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

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

test prop_output_has_nft_wrong_qty(
  vals via fuzz.both(cfuzz.policy_id(), fuzz.both(cfuzz.asset_name(), fuzz.int_between(2, 10))),
) {
  let (policy, rest) = vals
  let (name, qty) = rest
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.from_asset(policy, name, qty),
      datum:            NoDatum,
      reference_script: None,
    }
  !output_has_nft(output, policy, name)
}

test prop_seller_paid_exact(price via fuzz.int_between(1, 1000000)) {
  let seller = #"aabb"
  let addr = address.from_verification_key(seller)
  let output =
    Output {
      address:          addr,
      value:            assets.from_lovelace(price),
      datum:            NoDatum,
      reference_script: None,
    }
  seller_paid([output], seller, price)
}

test prop_seller_underpaid_fails(
  vals via fuzz.both(fuzz.int_between(2, 1000000), fuzz.int_between(1, 1000000)),
) {
  let (price, short) = vals
  let seller = #"aabb"
  let addr = address.from_verification_key(seller)
  let output =
    Output {
      address:          addr,
      value:            assets.from_lovelace(price - 1),
      datum:            NoDatum,
      reference_script: None,
    }
  if short >= price {
    True
  } else {
    !seller_paid([output], seller, price)
  }
}
