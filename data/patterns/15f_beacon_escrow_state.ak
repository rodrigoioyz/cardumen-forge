use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId, quantity_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}

pub type EscrowState {
  Funded
  InProgress
  Disputed
  Released
  Refunded
}

pub type EscrowRedeemer {
  Start
  Complete
  Dispute
  Resolve { release: Bool }
  Cancel
}

pub type EscrowDatum {
  escrow_state:  EscrowState,
  admin:         VerificationKeyHash,
  beacon_policy: PolicyId,
  beacon_name:   ByteArray,
}

fn valid_escrow_transition(
  from:     EscrowState,
  to:       EscrowState,
  redeemer: EscrowRedeemer,
) -> Bool {
  when redeemer is {
    Start      -> from == Funded && to == InProgress
    Complete   -> from == InProgress && to == Released
    Dispute    -> from == InProgress && to == Disputed
    Resolve { release } ->
      from == Disputed && (
        if release {
          to == Released
        } else {
          to == Refunded
        }
      )
    Cancel     -> from == Funded && to == Refunded
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

fn datum_from_output(output: Output) -> Option<EscrowDatum> {
  when output.datum is {
    InlineDatum(raw) -> {
      expect d: EscrowDatum = raw
      Some(d)
    }
    _ -> None
  }
}

validator beacon_escrow_state {
  spend(
    datum: Option<EscrowDatum>,
    redeemer: EscrowRedeemer,
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
    valid_escrow_transition(d.escrow_state, next_d.escrow_state, redeemer)
      && beacon_preserved(self.outputs, own_addr, d.beacon_policy, d.beacon_name)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_start_funded_to_inprogress() {
  valid_escrow_transition(Funded, InProgress, Start)
}

test prop_complete_inprogress_to_released() {
  valid_escrow_transition(InProgress, Released, Complete)
}

test prop_dispute_inprogress_to_disputed() {
  valid_escrow_transition(InProgress, Disputed, Dispute)
}

test prop_resolve_disputed_both_ways() {
  valid_escrow_transition(Disputed, Released, Resolve { release: True })
    && valid_escrow_transition(Disputed, Refunded, Resolve { release: False })
}
