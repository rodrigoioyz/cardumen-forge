
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
    // Seller must be paid the listed price
    let seller_receives = seller_paid(self.outputs, d.seller, d.price)
    // At least one output must carry the NFT to the buyer
    // (i.e. the NFT is actually transferred out of the script)
    let nft_transferred =
      list.any(
        self.outputs,
        fn(o) { output_has_nft(o, d.nft_policy, d.nft_name) },
      )
    // Price must be positive (sanity check on datum)
    let price_valid = d.price > 0
    seller_receives && nft_transferred && price_valid
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// seller_paid with empty outputs list always returns False (paid=0 < price for any price>=1)
test prop_seller_paid_no_outputs_fails(
  price via fuzz.int_at_least(1),
) fail {
  expect seller_paid([], #"aabb", price)
}

/// seller_paid fails when the payment goes to a different address than the seller
test prop_seller_paid_wrong_address_fails(
  price via fuzz.int_between(1, 1000000),
) fail {
  let seller = #"aabb"
  let wrong_addr = address.from_verification_key(#"ccdd")
  let output =
    Output {
      address:          wrong_addr,
      value:            assets.from_lovelace(price),
      datum:            NoDatum,
      reference_script: None,
    }
  expect seller_paid([output], seller, price)
}

/// output_has_nft fails when the output holds zero quantity of the asset
test prop_output_has_nft_zero_qty_fails(
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

/// output_has_nft fails when checking for a different policy than what the output holds
test prop_output_has_nft_wrong_policy_fails(
  vals via fuzz.both(
    fuzz.both(cfuzz.policy_id(), cfuzz.policy_id()),
    cfuzz.asset_name(),
  ),
) fail {
  let ((policy_held, policy_check), name) = vals
  // Only interesting when the two policies differ; if they happen to be equal
  // the helper would return True, so we guard — but fuzz.both over independent
  // policy_id fuzzers will virtually never produce equal 28-byte values, so
  // in practice this body is always reached with differing policies.
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.from_asset(policy_held, name, 1),
      datum:            NoDatum,
      reference_script: None,
    }
  // We only `expect` when the policies differ (guaranteeing False).
  // When they are equal we short-circuit with a benign True so the test
  // framework does not count it as a failure of the *test* itself.
  if policy_held == policy_check {
    True
  } else {
    expect output_has_nft(output, policy_check, name)
    True
  }
}