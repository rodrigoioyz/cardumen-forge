use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/transaction.{NoDatum, Output}

/// At least min_count outputs must satisfy a predicate
fn at_least_n_outputs(
  outputs:   List<Output>,
  min_count: Int,
  pred:      fn(Output) -> Bool,
) -> Bool {
  let count = list.foldl(
    outputs,
    0,
    fn(o, acc) { if pred(o) { acc + 1 } else { acc } },
  )
  count >= min_count
}

fn has_min_lovelace(output: Output, min_lovelace: Int) -> Bool {
  assets.lovelace_of(output.value) >= min_lovelace
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_all_outputs_count_satisfied(
  n via fuzz.int_between(1, 5),
) {
  let mk = fn(_: Int) {
    Output {
      address:          address.from_verification_key(#"aabb"),
      value:            assets.from_lovelace(2_000_000),
      datum:            NoDatum,
      reference_script: None,
    }
  }
  let outputs = list.map(list.range(0, n - 1), mk)
  at_least_n_outputs(outputs, n, fn(o) { has_min_lovelace(o, 1_000_000) })
}

test prop_empty_outputs_fail_min_count(
  min_count via fuzz.int_between(1, 5),
) {
  !at_least_n_outputs([], min_count, fn(_) { True })
}

test prop_zero_min_count_always_passes(
  n via fuzz.int_between(0, 5),
) {
  let outputs = list.map(list.range(0, n - 1), fn(_) {
    Output { address: address.from_verification_key(#"aabb"), value: assets.from_lovelace(1), datum: NoDatum, reference_script: None }
  })
  at_least_n_outputs(outputs, 0, fn(_) { True })
}

test prop_min_lovelace_predicate(
  lovelace via fuzz.int_between(1_000_000, 5_000_000),
) {
  let out = Output { address: address.from_verification_key(#"aabb"), value: assets.from_lovelace(lovelace), datum: NoDatum, reference_script: None }
  has_min_lovelace(out, 1_000_000)
}
