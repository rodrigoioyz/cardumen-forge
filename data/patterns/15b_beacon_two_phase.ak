
use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId, quantity_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}
pub type Phase {
  Open
  Paused
  Closed
}

pub type PhaseRedeemer {
  Advance
  Pause
  Resume
  Terminate
}

pub type PhaseDatum {
  phase:         Phase,
  admin:         VerificationKeyHash,
  beacon_policy: PolicyId,
  beacon_name:   ByteArray,
}

/// Open→Paused (Pause), Paused→Open (Resume), Open→Closed (Advance), any→Closed (Terminate)
fn valid_phase_transition(from: Phase, to: Phase, redeemer: PhaseRedeemer) -> Bool {
  when redeemer is {
    Advance   -> from == Open && to == Closed
    Pause     -> from == Open && to == Paused
    Resume    -> from == Paused && to == Open
    Terminate -> to == Closed
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

fn phase_from_output(output: Output) -> Option<PhaseDatum> {
  when output.datum is {
    InlineDatum(raw) -> {
      expect d: PhaseDatum = raw
      Some(d)
    }
    _ -> None
  }
}

validator beacon_two_phase {
  spend(
    datum: Option<PhaseDatum>,
    redeemer: PhaseRedeemer,
    own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    expect Some(own_input) =
      list.find(self.inputs, fn(i) { i.output_reference == own_ref })
    let own_addr = own_input.output.address
    expect Some(next_output) =
      list.find(self.outputs, fn(o) { o.address == own_addr })
    expect Some(next_d) = phase_from_output(next_output)
    valid_phase_transition(d.phase, next_d.phase, redeemer)
      && beacon_preserved(self.outputs, own_addr, d.beacon_policy, d.beacon_name)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_advance_open_to_closed() {
  valid_phase_transition(Open, Closed, Advance)
}

test prop_pause_open_to_paused() {
  valid_phase_transition(Open, Paused, Pause)
}

test prop_resume_paused_to_open() {
  valid_phase_transition(Paused, Open, Resume)
}

test prop_terminate_always_closed() {
  valid_phase_transition(Open, Closed, Terminate)
    && valid_phase_transition(Paused, Closed, Terminate)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// Advance requires from==Open; Closed→Closed is invalid
test prop_advance_closed_rejected() fail {
  expect valid_phase_transition(Closed, Closed, Advance)
}

// Pause requires from==Open; Paused→Paused is invalid
test prop_pause_paused_rejected() fail {
  expect valid_phase_transition(Paused, Paused, Pause)
}

// Resume requires from==Paused; Open→Open is invalid
test prop_resume_open_rejected() fail {
  expect valid_phase_transition(Open, Open, Resume)
}

// beacon_preserved always returns False when outputs list is empty,
// regardless of which policy/name we ask for
test prop_beacon_not_preserved_empty_outputs(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  let addr =
    address.from_verification_key(
      #"00000000000000000000000000000000000000000000000000000000",
    )
  expect beacon_preserved([], addr, policy, name)
}