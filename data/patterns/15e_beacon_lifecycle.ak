use aiken/collection/list
use aiken/crypto.{VerificationKeyHash}
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId, quantity_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}

pub type Lifecycle {
  Created
  Active
  Suspended
  Expired
  Terminated
}

pub type LifecycleRedeemer {
  Activate
  Suspend
  Reactivate
  Expire
  Terminate
}

pub type LifecycleDatum {
  lifecycle:     Lifecycle,
  admin:         VerificationKeyHash,
  beacon_policy: PolicyId,
  beacon_name:   ByteArray,
}

fn valid_lifecycle_transition(
  from:     Lifecycle,
  to:       Lifecycle,
  redeemer: LifecycleRedeemer,
) -> Bool {
  when redeemer is {
    Activate    -> from == Created && to == Active
    Suspend     -> from == Active && to == Suspended
    Reactivate  -> from == Suspended && to == Active
    Expire      -> ( from == Active || from == Suspended ) && to == Expired
    Terminate   -> to == Terminated
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

fn datum_from_output(output: Output) -> Option<LifecycleDatum> {
  when output.datum is {
    InlineDatum(raw) -> {
      expect d: LifecycleDatum = raw
      Some(d)
    }
    _ -> None
  }
}

validator beacon_lifecycle {
  spend(
    datum: Option<LifecycleDatum>,
    redeemer: LifecycleRedeemer,
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
    valid_lifecycle_transition(d.lifecycle, next_d.lifecycle, redeemer)
      && beacon_preserved(self.outputs, own_addr, d.beacon_policy, d.beacon_name)
      && list.has(self.extra_signatories, d.admin)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_activate_created_to_active() {
  valid_lifecycle_transition(Created, Active, Activate)
}

test prop_suspend_active_to_suspended() {
  valid_lifecycle_transition(Active, Suspended, Suspend)
}

test prop_reactivate_suspended_to_active() {
  valid_lifecycle_transition(Suspended, Active, Reactivate)
}

test prop_expire_from_active_or_suspended() {
  valid_lifecycle_transition(Active, Expired, Expire)
    && valid_lifecycle_transition(Suspended, Expired, Expire)
}
