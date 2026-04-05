
use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/assets.{AssetName, PolicyId, lovelace_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output, OutputReference, Transaction}
pub type NftLoanDatum {
  nft_policy:  PolicyId,
  nft_name:    AssetName,
  loan_amount: Int,
  borrower:    ByteArray,
}

pub type NftLoanRedeemer {
  Repay
  Default
}

/// True when the output carries exactly 1 of the specified NFT
fn output_has_nft(
  output:  Output,
  policy:  PolicyId,
  name:    AssetName,
) -> Bool {
  assets.quantity_of(output.value, policy, name) == 1
}

/// Find an output going to borrower with enough lovelace
fn borrower_repays(
  outputs:      List<Output>,
  borrower_key: ByteArray,
  amount:       Int,
) -> Bool {
  let addr = address.from_verification_key(borrower_key)
  let paid =
    list.foldl(
      list.filter(outputs, fn(o) { o.address == addr }),
      0,
      fn(o, acc) { acc + lovelace_of(o.value) },
    )
  paid >= amount
}

validator nft_collateral_loan {
  spend(
    datum: Option<NftLoanDatum>,
    redeemer: NftLoanRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      Repay ->
        // Borrower returns loan_amount → receives the NFT back
        borrower_repays(self.outputs, d.borrower, d.loan_amount)
      Default ->
        // Lender keeps NFT — borrower must NOT sign (anyone can trigger)
        !list.has(self.extra_signatories, d.borrower)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_output_has_nft_correct(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let val    = assets.from_asset(policy, name, 1)
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            val,
      datum:            NoDatum,
      reference_script: None,
    }
  output_has_nft(output, policy, name)
}

test prop_output_has_nft_wrong_qty(
  vals via fuzz.both(cfuzz.policy_id(), fuzz.both(cfuzz.asset_name(), fuzz.int_between(2, 10))),
) {
  let (policy, name_qty) = vals
  let (name, qty) = name_qty
  let val    = assets.from_asset(policy, name, qty)
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            val,
      datum:            NoDatum,
      reference_script: None,
    }
  !output_has_nft(output, policy, name)
}

test prop_output_has_nft_zero_qty(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let val    = assets.from_lovelace(2000000)
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            val,
      datum:            NoDatum,
      reference_script: None,
    }
  !output_has_nft(output, policy, name)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// output_has_nft must reject an output holding 0 of the NFT (lovelace-only value)
test prop_fail_output_has_nft_zero(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.from_lovelace(2000000),
      datum:            NoDatum,
      reference_script: None,
    }
  expect output_has_nft(output, policy, name)
}

/// output_has_nft must reject an output holding qty >= 2 of the NFT
test prop_fail_output_has_nft_excess_qty(
  vals via fuzz.both(
    cfuzz.policy_id(),
    fuzz.both(cfuzz.asset_name(), fuzz.int_between(2, 100)),
  ),
) fail {
  let (policy, name_qty) = vals
  let (name, qty) = name_qty
  let output =
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.from_asset(policy, name, qty),
      datum:            NoDatum,
      reference_script: None,
    }
  expect output_has_nft(output, policy, name)
}

/// borrower_repays must reject when there are no outputs at all
test prop_fail_borrower_repays_no_outputs(
  vals via fuzz.both(cfuzz.verification_key_hash(), fuzz.int_at_least(1)),
) fail {
  let (borrower_key, amount) = vals
  expect borrower_repays([], borrower_key, amount)
}

/// borrower_repays must reject when the paid lovelace is strictly less than amount
test prop_fail_borrower_repays_insufficient(
  vals via fuzz.both(
    cfuzz.verification_key_hash(),
    fuzz.int_between(1, 1000000),
  ),
) fail {
  let (borrower_key, shortfall) = vals
  // We require amount = paid + shortfall, so paid < amount always
  let amount = 5000000 + shortfall
  let paid   = 5000000
  let addr   = address.from_verification_key(borrower_key)
  let output =
    Output {
      address:          addr,
      value:            assets.from_lovelace(paid),
      datum:            NoDatum,
      reference_script: None,
    }
  expect borrower_repays([output], borrower_key, amount)
}