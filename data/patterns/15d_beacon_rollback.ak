use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId, quantity_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}

pub type Step {
  Step0
  Step1
  Step2
  Step3
}

pub type StepRedeemer {
  Next
  Rollback
  Abort
}

pub type StepDatum {
  step:          Step,
  admin:         VerificationKeyHash,
  beacon_policy: PolicyId,
  beacon_name:   ByteArray,
}

/// Next advances, Rollback goes one step back, Abort resets to Step0
fn valid_step_transition(from: Step, to: Step, redeemer: StepRedeemer) -> Bool {
  when redeemer is {
    Next ->
      when from is {
        Step0 -> to == Step1
        Step1 -> to == Step2
        Step2 -> to == Step3
        Step3 -> False
      }
    Rollback ->
      when from is {
        Step0 -> False
        Step1 -> to == Step0
        Step2 -> to == Step1
        Step3 -> to == Step2
      }
    Abort -> to == Step0
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

fn datum_from_output(output: Output) -> Option<StepDatum> {
  when output.datum is {
    InlineDatum(raw) -> {
      expect d: StepDatum = raw
      Some(d)
    }
    _ -> None
  }
}

validator beacon_rollback {
  spend(
    datum: Option<StepDatum>,
    redeemer: StepRedeemer,
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
    valid_step_transition(d.step, next_d.step, redeemer)
      && beacon_preserved(self.outputs, own_addr, d.beacon_policy, d.beacon_name)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_next_advances() {
  valid_step_transition(Step0, Step1, Next)
    && valid_step_transition(Step1, Step2, Next)
    && valid_step_transition(Step2, Step3, Next)
}

test prop_rollback_goes_back() {
  valid_step_transition(Step1, Step0, Rollback)
    && valid_step_transition(Step2, Step1, Rollback)
    && valid_step_transition(Step3, Step2, Rollback)
}

test prop_abort_resets_to_step0() {
  valid_step_transition(Step2, Step0, Abort)
    && valid_step_transition(Step3, Step0, Abort)
}

test prop_step3_next_fails() {
  !valid_step_transition(Step3, Step3, Next)
}
