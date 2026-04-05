use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId, quantity_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}

pub type State {
  Idle
  Active
  Locked
  Closing
}

pub type StateRedeemer {
  Advance
  Reset
  Terminate
}

pub type MachineDatum {
  state:        State,
  admin:        VerificationKeyHash,
  beacon_policy: PolicyId,
  beacon_name:  ByteArray,
}

/// Valid transitions: Idle→Active, Active→Locked, Locked→Closing
fn valid_transition(from: State, to: State, redeemer: StateRedeemer) -> Bool {
  when redeemer is {
    Advance ->
      when from is {
        Idle    -> to == Active
        Active  -> to == Locked
        Locked  -> to == Closing
        Closing -> False
      }
    Reset     -> to == Idle
    Terminate -> to == Closing
  }
}

/// The beacon NFT must be present in the continuing output
fn beacon_preserved(
  outputs:      List<Output>,
  own_addr:     address.Address,
  beacon_policy: PolicyId,
  beacon_name:  ByteArray,
) -> Bool {
  list.any(
    outputs,
    fn(o) {
      o.address == own_addr
        && quantity_of(o.value, beacon_policy, beacon_name) == 1
    },
  )
}

fn state_from_output(output: Output) -> Option<MachineDatum> {
  when output.datum is {
    InlineDatum(raw) -> {
      expect d: MachineDatum = raw
      Some(d)
    }
    _ -> None
  }
}

validator beacon_state_machine {
  spend(
    datum: Option<MachineDatum>,
    redeemer: StateRedeemer,
    own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    // Find own input to get address
    expect Some(own_input) =
      list.find(self.inputs, fn(i) { i.output_reference == own_ref })
    let own_addr = own_input.output.address
    // Find continuing output with new datum
    expect Some(next_output) =
      list.find(self.outputs, fn(o) { o.address == own_addr })
    expect Some(next_d) = state_from_output(next_output)
    // Validate
    valid_transition(d.state, next_d.state, redeemer)
      && beacon_preserved(self.outputs, own_addr, d.beacon_policy, d.beacon_name)
      && (
        when redeemer is {
          Advance -> True
          Reset   -> list.has(self.extra_signatories, d.admin)
          Terminate -> list.has(self.extra_signatories, d.admin)
        }
      )
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_valid_transition_advance_idle() {
  valid_transition(Idle, Active, Advance)
}

test prop_valid_transition_advance_active() {
  valid_transition(Active, Locked, Advance)
}

test prop_valid_transition_advance_locked() {
  valid_transition(Locked, Closing, Advance)
}

test prop_valid_transition_closing_advance_fails() {
  !valid_transition(Closing, Idle, Advance)
}

test prop_valid_transition_reset_always_to_idle() {
  valid_transition(Active, Idle, Reset)
    && valid_transition(Locked, Idle, Reset)
    && valid_transition(Closing, Idle, Reset)
}

test prop_valid_transition_wrong_target_fails() {
  !valid_transition(Idle, Locked, Advance)
}
