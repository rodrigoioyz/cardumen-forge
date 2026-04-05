
/// Continuing output must carry the NFT and have an InlineDatum
use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{InlineDatum, NoDatum, Output}
fn has_inline_datum(output: Output) -> Bool {
  when output.datum is {
    InlineDatum(_) -> True
    _              -> False
  }
}

fn thread_output_valid(
  output:      Output,
  auth_policy: PolicyId,
  auth_name:   ByteArray,
) -> Bool {
  assets.quantity_of(output.value, auth_policy, auth_name) == 1
    && has_inline_datum(output)
}

fn find_thread_output(
  outputs:     List<Output>,
  auth_policy: PolicyId,
  auth_name:   ByteArray,
) -> Bool {
  list.any(outputs, fn(o) { thread_output_valid(o, auth_policy, auth_name) })
}

// ── Validator ────────────────────────────────────────────────────────────────

pub type ThreadDatum {
  auth_policy: PolicyId,
  auth_name: ByteArray,
}

pub type ThreadRedeemer {
  Update
}

validator thread_nft_datum_update {
  spend(
    datum: Option<ThreadDatum>,
    _redeemer: ThreadRedeemer,
    _utxo: Data,
    self: transaction.Transaction,
  ) {
    expect Some(d) = datum
    // There must be at least one output in the transaction
    let outputs_non_empty = !list.is_empty(self.outputs)
    // Every output that carries the thread NFT must also have an inline datum
    let all_thread_outputs_have_datum =
      list.all(
        self.outputs,
        fn(o) {
          let qty = assets.quantity_of(o.value, d.auth_policy, d.auth_name)
          if qty == 1 {
            has_inline_datum(o)
          } else {
            True
          }
        },
      )
    // At least one continuing output must carry the NFT with an inline datum
    let thread_continues =
      find_thread_output(self.outputs, d.auth_policy, d.auth_name)
    outputs_non_empty && all_thread_outputs_have_datum && thread_continues
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_output_with_nft_and_inline_datum_valid(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let val = assets.from_asset(policy, name, 1)
  let out = Output {
    address:          address.from_verification_key(#"aabb"),
    value:            val,
    datum:            InlineDatum(42),
    reference_script: None,
  }
  thread_output_valid(out, policy, name)
}

test prop_output_no_datum_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let val = assets.from_asset(policy, name, 1)
  let out = Output {
    address:          address.from_verification_key(#"aabb"),
    value:            val,
    datum:            NoDatum,
    reference_script: None,
  }
  !thread_output_valid(out, policy, name)
}

test prop_find_thread_output_true(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) {
  let (policy, name) = vals
  let val = assets.from_asset(policy, name, 1)
  let out = Output {
    address:          address.from_verification_key(#"aabb"),
    value:            val,
    datum:            InlineDatum(0),
    reference_script: None,
  }
  find_thread_output([out], policy, name)
}

test prop_find_thread_output_empty_false() {
  !find_thread_output([], #"aabb", #"ccdd")
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// An output with the NFT but NoDatum must always be rejected by thread_output_valid
test prop_no_datum_output_always_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  let val = assets.from_asset(policy, name, 1)
  let out = Output {
    address:          address.from_verification_key(#"aabb"),
    value:            val,
    datum:            NoDatum,
    reference_script: None,
  }
  expect thread_output_valid(out, policy, name)
}

/// find_thread_output over an empty list must always return False
test prop_find_thread_output_empty_always_fails(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  expect find_thread_output([], policy, name)
}

/// An output carrying zero quantity of the NFT (ada-only) with InlineDatum
/// must be rejected — quantity_of returns 0, not 1
test prop_zero_qty_output_always_rejected(
  vals via fuzz.both(cfuzz.policy_id(), cfuzz.asset_name()),
) fail {
  let (policy, name) = vals
  let out = Output {
    address:          address.from_verification_key(#"aabb"),
    value:            assets.zero,
    datum:            InlineDatum(99),
    reference_script: None,
  }
  expect thread_output_valid(out, policy, name)
}

/// A list containing only an output with wrong policy/name and InlineDatum
/// must fail find_thread_output for a different policy/name pair
test prop_wrong_policy_not_found() fail {
  let policy_a = #"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  let policy_b = #"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  let name = #"ccdd"
  let val = assets.from_asset(policy_a, name, 1)
  let out = Output {
    address:          address.from_verification_key(#"aabb"),
    value:            val,
    datum:            InlineDatum(0),
    reference_script: None,
  }
  expect find_thread_output([out], policy_b, name)
}