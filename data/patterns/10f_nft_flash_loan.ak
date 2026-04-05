use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/assets.{AssetName, PolicyId, lovelace_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output, OutputReference, Transaction}

pub type FlashLoanDatum {
  lender:     ByteArray,
  nft_policy: PolicyId,
  nft_name:   AssetName,
  principal:  Int,
  fee:        Int,
}

fn output_has_nft(output: Output, policy: PolicyId, name: AssetName) -> Bool {
  assets.quantity_of(output.value, policy, name) == 1
}

/// Flash loan: NFT must be returned AND lender receives principal + fee in same tx
fn flash_loan_repaid(
  outputs:   List<Output>,
  lender:    ByteArray,
  policy:    PolicyId,
  name:      AssetName,
  principal: Int,
  fee:       Int,
) -> Bool {
  let addr = address.from_verification_key(lender)
  let lender_outputs = list.filter(outputs, fn(o) { o.address == addr })
  let total_paid =
    list.foldl(lender_outputs, 0, fn(o, acc) { acc + lovelace_of(o.value) })
  let nft_returned = list.any(lender_outputs, fn(o) { output_has_nft(o, policy, name) })
  total_paid >= principal + fee && nft_returned
}

/// Total repayment required
fn repayment_total(principal: Int, fee: Int) -> Int {
  principal + fee
}

validator nft_flash_loan {
  spend(
    datum: Option<FlashLoanDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    flash_loan_repaid(
      self.outputs,
      d.lender,
      d.nft_policy,
      d.nft_name,
      d.principal,
      d.fee,
    )
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_repayment_total(
  vals via fuzz.both(fuzz.int_between(0, 1000000), fuzz.int_between(0, 10000)),
) {
  let (principal, fee) = vals
  repayment_total(principal, fee) == principal + fee
}

test prop_repayment_total_gte_principal(
  vals via fuzz.both(fuzz.int_between(0, 1000000), fuzz.int_between(0, 10000)),
) {
  let (principal, fee) = vals
  repayment_total(principal, fee) >= principal
}

test prop_flash_loan_repaid_correct(
  vals via fuzz.both(cfuzz.policy_id(), fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000000))),
) {
  let (policy, rest) = vals
  let (name, principal) = rest
  let lender = #"aabb"
  let fee = 1000
  let addr = address.from_verification_key(lender)
  let output =
    Output {
      address:          addr,
      value:            assets.merge(
        assets.from_asset(policy, name, 1),
        assets.from_lovelace(principal + fee),
      ),
      datum:            NoDatum,
      reference_script: None,
    }
  flash_loan_repaid([output], lender, policy, name, principal, fee)
}

test prop_flash_loan_missing_nft_fails(
  vals via fuzz.both(cfuzz.policy_id(), fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000000))),
) {
  let (policy, rest) = vals
  let (name, principal) = rest
  let lender = #"aabb"
  let fee = 1000
  let addr = address.from_verification_key(lender)
  let output =
    Output {
      address:          addr,
      value:            assets.from_lovelace(principal + fee),
      datum:            NoDatum,
      reference_script: None,
    }
  !flash_loan_repaid([output], lender, policy, name, principal, fee)
}
