
/// Extract an integer counter from an InlineDatum
use aiken/fuzz
use aiken/collection/list
use cardano/address
use cardano/assets
use cardano/transaction.{InlineDatum, Input, Output, Transaction}
fn get_counter(output: Output) -> Option<Int> {
  when output.datum is {
    InlineDatum(raw) -> {
      expect n: Int = raw
      Some(n)
    }
    _ -> None
  }
}

/// Counter in new output must be exactly old_counter + 1
fn counter_incremented(old_output: Output, new_output: Output) -> Bool {
  when (get_counter(old_output), get_counter(new_output)) is {
    (Some(old), Some(new)) -> new == old + 1
    _                      -> False
  }
}

// ── Validator ────────────────────────────────────────────────────────────────

/// Thread NFT counter: the script ensures that each time the UTxO is spent,
/// the counter stored in the datum is incremented by exactly 1.
/// The redeemer carries the policy id of the thread NFT (used to identify
/// the continuing output that holds the token).
validator thread_nft_counter {
  spend(
    datum: Option<Data>,
    _redeemer: Data,
    own_ref: transaction.OutputReference,
    self: Transaction,
  ) {
    expect Some(_) = datum

    // Find the input being spent so we can recover its output
    expect Some(own_input) =
      list.find(self.inputs, fn(i: Input) { i.output_reference == own_ref })

    let own_addr = own_input.output.address

    // Find the continuing output at the same address
    expect Some(continuing) =
      list.find(self.outputs, fn(o: Output) { o.address == own_addr })

    counter_incremented(own_input.output, continuing)
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_get_counter_from_inline_datum(
  n via fuzz.int_between(0, 1000),
) {
  let out = Output {
    address:          address.from_verification_key(#"aabb"),
    value:            assets.from_lovelace(2_000_000),
    datum:            InlineDatum(n),
    reference_script: None,
  }
  get_counter(out) == Some(n)
}

test prop_counter_incremented_valid(
  n via fuzz.int_between(0, 999),
) {
  let old_out = Output { address: address.from_verification_key(#"aabb"), value: assets.from_lovelace(1), datum: InlineDatum(n), reference_script: None }
  let new_out = Output { address: address.from_verification_key(#"aabb"), value: assets.from_lovelace(1), datum: InlineDatum(n + 1), reference_script: None }
  counter_incremented(old_out, new_out)
}

test prop_counter_same_rejected(
  n via fuzz.int_between(0, 999),
) {
  let out = Output { address: address.from_verification_key(#"aabb"), value: assets.from_lovelace(1), datum: InlineDatum(n), reference_script: None }
  !counter_incremented(out, out)
}

test prop_counter_skipped_rejected(
  n via fuzz.int_between(0, 997),
) {
  let old_out = Output { address: address.from_verification_key(#"aabb"), value: assets.from_lovelace(1), datum: InlineDatum(n), reference_script: None }
  let new_out = Output { address: address.from_verification_key(#"aabb"), value: assets.from_lovelace(1), datum: InlineDatum(n + 2), reference_script: None }
  !counter_incremented(old_out, new_out)
}

// ── Negative (fail) property tests ───────────────────────────────────────────

/// counter_incremented must reject when new == old (no increment at all)
test prop_fail_counter_same(
  n via fuzz.int_between(0, 999),
) fail {
  let out =
    Output {
      address: address.from_verification_key(#"aabb"),
      value: assets.from_lovelace(1),
      datum: InlineDatum(n),
      reference_script: None,
    }
  expect counter_incremented(out, out)
}

/// counter_incremented must reject when new == old + 2 (skipped a step)
test prop_fail_counter_skipped(
  n via fuzz.int_between(0, 997),
) fail {
  let old_out =
    Output {
      address: address.from_verification_key(#"aabb"),
      value: assets.from_lovelace(1),
      datum: InlineDatum(n),
      reference_script: None,
    }
  let new_out =
    Output {
      address: address.from_verification_key(#"aabb"),
      value: assets.from_lovelace(1),
      datum: InlineDatum(n + 2),
      reference_script: None,
    }
  expect counter_incremented(old_out, new_out)
}

/// counter_incremented must reject when new == old - 1 (counter went backwards)
test prop_fail_counter_decremented(
  n via fuzz.int_between(1, 1000),
) fail {
  let old_out =
    Output {
      address: address.from_verification_key(#"aabb"),
      value: assets.from_lovelace(1),
      datum: InlineDatum(n),
      reference_script: None,
    }
  let new_out =
    Output {
      address: address.from_verification_key(#"aabb"),
      value: assets.from_lovelace(1),
      datum: InlineDatum(n - 1),
      reference_script: None,
    }
  expect counter_incremented(old_out, new_out)
}

/// counter_incremented must reject when the new counter is a large positive jump
test prop_fail_counter_large_jump(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(2, 1000)),
) fail {
  let (n, jump) = vals
  let old_out =
    Output {
      address: address.from_verification_key(#"aabb"),
      value: assets.from_lovelace(1),
      datum: InlineDatum(n),
      reference_script: None,
    }
  let new_out =
    Output {
      address: address.from_verification_key(#"aabb"),
      value: assets.from_lovelace(1),
      datum: InlineDatum(n + jump),
      reference_script: None,
    }
  expect counter_incremented(old_out, new_out)
}