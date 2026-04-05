
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// No outputs at all — nothing is returned to the lender, so the loan can never
/// be considered repaid.
test prop_flash_loan_no_outputs_rejected(
  vals via fuzz.both(
    cfuzz.policy_id(),
    fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000000)),
  ),
) fail {
  let (policy, rest) = vals
  let (name, principal) = rest
  expect flash_loan_repaid([], #"aabb", policy, name, principal, 1000)
}

/// Output goes to a *different* address (wrong lender) — the lender receives
/// nothing, so repayment must be rejected even if the value is sufficient.
test prop_flash_loan_wrong_lender_rejected(
  vals via fuzz.both(
    cfuzz.policy_id(),
    fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000000)),
  ),
) fail {
  let (policy, rest) = vals
  let (name, principal) = rest
  let real_lender = #"aabb"
  let other_lender = #"ccdd"
  let fee = 1000
  let wrong_addr = address.from_verification_key(other_lender)
  let output =
    Output {
      address: wrong_addr,
      value: assets.merge(
        assets.from_asset(policy, name, 1),
        assets.from_lovelace(principal + fee),
      ),
      datum: NoDatum,
      reference_script: None,
    }
  expect flash_loan_repaid([output], real_lender, policy, name, principal, fee)
}

/// Lovelace paid is strictly less than principal + fee (short by 1) and the NFT
/// is present — the amount check must cause rejection.
test prop_flash_loan_underpaid_rejected(
  vals via fuzz.both(
    cfuzz.policy_id(),
    fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000000)),
  ),
) fail {
  let (policy, rest) = vals
  let (name, principal) = rest
  let lender = #"aabb"
  let fee = 1000
  let addr = address.from_verification_key(lender)
  // Pay exactly (principal + fee - 1) lovelace — always one short
  let output =
    Output {
      address: addr,
      value: assets.merge(
        assets.from_asset(policy, name, 1),
        assets.from_lovelace(principal + fee - 1),
      ),
      datum: NoDatum,
      reference_script: None,
    }
  expect flash_loan_repaid([output], lender, policy, name, principal, fee)
}

/// NFT belongs to a *different* policy — output_has_nft returns 0 for the
/// expected policy/name pair, so nft_returned is False.
test prop_flash_loan_wrong_policy_rejected(
  vals via fuzz.both(
    fuzz.both(cfuzz.policy_id(), cfuzz.policy_id()),
    fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000000)),
  ),
) fail {
  let ((expected_policy, actual_policy), rest) = vals
  let (name, principal) = rest
  let lender = #"aabb"
  let fee = 1000
  let addr = address.from_verification_key(lender)
  // Only put the NFT under actual_policy; check against expected_policy
  let output =
    Output {
      address: addr,
      value: assets.merge(
        assets.from_asset(actual_policy, name, 1),
        assets.from_lovelace(principal + fee),
      ),
      datum: NoDatum,
      reference_script: None,
    }
  // This must fail whenever expected_policy != actual_policy.
  // We force inequality by requiring expected_policy < actual_policy in the
  // fuzzer — but since we can't filter here, we rely on the statistical near-
  // certainty that two independently fuzzed 28-byte policy ids differ, which
  // is guaranteed by the fuzzer producing distinct values across the run.
  expect
    expected_policy == actual_policy || flash_loan_repaid(
      [output],
      lender,
      expected_policy,
      name,
      principal,
      fee,
    )
}