
use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId, quantity_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}
pub type ApprovalState {
  Draft
  Review
  Approved
  Rejected
}

pub type ApprovalRedeemer {
  Submit
  Approve
  Reject
  Revise
}

pub type ApprovalDatum {
  state:         ApprovalState,
  admin:         VerificationKeyHash,
  beacon_policy: PolicyId,
  beacon_name:   ByteArray,
}

fn valid_approval_transition(
  from:     ApprovalState,
  to:       ApprovalState,
  redeemer: ApprovalRedeemer,
) -> Bool {
  when redeemer is {
    Submit  -> from == Draft && to == Review
    Approve -> from == Review && to == Approved
    Reject  -> from == Review && to == Rejected
    Revise  -> from == Rejected && to == Draft
  }
}

fn beacon_preserved(
  outputs:       List<Output>,
  own_addr:      address.Address,
  beacon_policy: PolicyId,
  beacon_name:   ByteArray,
) -> Bool {
  list.any(
    outputs,
    fn(o) {
      o.address == own_addr
        && quantity_of(o.value, beacon_policy, beacon_name) == 1
    },
  )
}

fn datum_from_output(output: Output) -> Option<ApprovalDatum> {
  when output.datum is {
    InlineDatum(raw) -> {
      expect d: ApprovalDatum = raw
      Some(d)
    }
    _ -> None
  }
}

validator beacon_approval {
  spend(
    datum: Option<ApprovalDatum>,
    redeemer: ApprovalRedeemer,
    own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    expect Some(own_input) =
      list.find(self.inputs, fn(i) { i.output_reference == own_ref })
    let own_addr = own_input.output.address
    expect Some(next_output) =
      list.find(self.outputs, fn(o) { o.address == own_addr })
    expect Some(next_d) = datum_from_output(next_output)
    valid_approval_transition(d.state, next_d.state, redeemer)
      && beacon_preserved(self.outputs, own_addr, d.beacon_policy, d.beacon_name)
      && list.has(self.extra_signatories, d.admin)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_submit_draft_to_review() {
  valid_approval_transition(Draft, Review, Submit)
}

test prop_approve_review_to_approved() {
  valid_approval_transition(Review, Approved, Approve)
}

test prop_reject_review_to_rejected() {
  valid_approval_transition(Review, Rejected, Reject)
}

test prop_revise_rejected_to_draft() {
  valid_approval_transition(Rejected, Draft, Revise)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// Submit requires Draft→Review; using Approved as source always fails.
test prop_submit_from_approved_rejected(
  _unused via fuzz.bool(),
) fail {
  expect valid_approval_transition(Approved, Review, Submit)
}

// Approve requires Review→Approved; starting from Draft always fails.
test prop_approve_from_draft_rejected(
  _unused via fuzz.bool(),
) fail {
  expect valid_approval_transition(Draft, Approved, Approve)
}

// Revise requires Rejected→Draft; starting from Review always fails.
test prop_revise_from_review_rejected(
  _unused via fuzz.bool(),
) fail {
  expect valid_approval_transition(Review, Draft, Revise)
}

// beacon_preserved over an empty output list always returns False.
test prop_beacon_preserved_no_outputs_fails(
  pair via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (pol, name) = pair
  let addr =
    address.from_verification_key(
      #"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
  expect beacon_preserved([], addr, pol, name)
}