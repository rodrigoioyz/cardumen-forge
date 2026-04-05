use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{InlineDatum, NoDatum, Output}

/// Continuing output must carry the NFT and have an InlineDatum
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
