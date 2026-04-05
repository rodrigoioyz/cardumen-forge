
/// At least min_count outputs must satisfy a predicate
use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/transaction.{NoDatum, Output}
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

pub type BatchDatum {
  min_output_count: Int,
  min_lovelace_each: Int,
}

validator batch_min_outputs {
  spend(
    datum: Option<BatchDatum>,
    _redeemer: Data,
    _utxo: transaction.OutputReference,
    self: transaction.Transaction,
  ) {
    expect Some(d) = datum
    let outputs = self.outputs
    at_least_n_outputs(
      outputs,
      d.min_output_count,
      fn(o) { has_min_lovelace(o, d.min_lovelace_each) },
    )
  }

  else(_) {
    fail
  }
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Empty output list never satisfies a positive min_count requirement
test prop_empty_outputs_never_satisfy_positive_min_count(
  min_count via fuzz.int_between(1, 20),
) fail {
  expect at_least_n_outputs([], min_count, fn(_) { True })
}

/// Output with lovelace strictly below the threshold must be rejected
test prop_output_below_min_lovelace_rejected(
  vals via fuzz.both(fuzz.int_between(0, 999_999), fuzz.int_between(1_000_000, 5_000_000)),
) fail {
  let (low_lovelace, threshold) = vals
  let out =
    Output {
      address: address.from_verification_key(#"aabb"),
      value: assets.from_lovelace(low_lovelace),
      datum: NoDatum,
      reference_script: None,
    }
  expect has_min_lovelace(out, threshold)
}

/// One output that is below the lovelace threshold cannot satisfy min_count=1
test prop_single_low_output_fails_at_least_n(
  vals via fuzz.both(fuzz.int_between(0, 499_999), fuzz.int_between(500_000, 2_000_000)),
) fail {
  let (low_lovelace, threshold) = vals
  let out =
    Output {
      address: address.from_verification_key(#"aabb"),
      value: assets.from_lovelace(low_lovelace),
      datum: NoDatum,
      reference_script: None,
    }
  expect at_least_n_outputs([out], 1, fn(o) { has_min_lovelace(o, threshold) })
}

/// More outputs required than actually provided all passing the predicate
test prop_insufficient_passing_outputs(
  vals via fuzz.both(fuzz.int_between(1, 4), fuzz.int_between(5, 10)),
) fail {
  let (n_outputs, min_count) = vals
  let mk = fn(_: Int) {
    Output {
      address: address.from_verification_key(#"aabb"),
      value: assets.from_lovelace(2_000_000),
      datum: NoDatum,
      reference_script: None,
    }
  }
  let outputs = list.map(list.range(0, n_outputs - 1), mk)
  expect at_least_n_outputs(outputs, min_count, fn(o) { has_min_lovelace(o, 1_000_000) })
}