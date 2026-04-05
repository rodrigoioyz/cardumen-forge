use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/transaction.{InlineDatum, Output}

/// Extract an integer counter from an InlineDatum
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
