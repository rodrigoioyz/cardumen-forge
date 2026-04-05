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
