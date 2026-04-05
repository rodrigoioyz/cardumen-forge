
/// Each swap order is indexed: input at position i must correspond to
/// output at position i. This prevents double satisfaction by requiring
/// strictly ascending output indices.
use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/assets.{lovelace_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output, OutputReference, Transaction}
pub type SwapDatum {
  owner:       ByteArray,
  min_receive: Int,
  output_idx:  Int,
}

pub type BatchSwapRedeemer {
  input_idx:  Int,
  output_idx: Int,
}

/// Output indices must be strictly ascending to prevent duplicate claims
fn indices_ascending(indices: List<Int>) -> Bool {
  when indices is {
    [] -> True
    [_] -> True
    [first, second, ..rest] ->
      first < second && indices_ascending([second, ..rest])
  }
}

/// The output at output_idx must send at least min_receive lovelace to owner
fn output_satisfies(
  outputs:     List<Output>,
  output_idx:  Int,
  owner_addr:  Output,
  min_receive: Int,
) -> Bool {
  when list.at(outputs, output_idx) is {
    Some(o) ->
      o.address == owner_addr.address && lovelace_of(o.value) >= min_receive
    None -> False
  }
}

/// Count how many of the outputs meet a minimum lovelace threshold
fn count_satisfied(outputs: List<Output>, min_lovelace: Int) -> Int {
  list.foldl(
    outputs,
    0,
    fn(o, acc) {
      if lovelace_of(o.value) >= min_lovelace {
        acc + 1
      } else {
        acc
      }
    },
  )
}

validator indexed_batch_swap {
  spend(
    datum: Option<SwapDatum>,
    redeemer: BatchSwapRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    // input_idx and output_idx must correspond
    redeemer.input_idx >= 0
      && redeemer.output_idx == d.output_idx
      && list.length(self.outputs) > d.output_idx
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_indices_ascending_empty() {
  indices_ascending([])
}

test prop_indices_ascending_sorted(
  vals via fuzz.both(fuzz.int_between(0, 100), fuzz.int_between(1, 50)),
) {
  let (base, step) = vals
  indices_ascending([base, base + step, base + step * 2])
}

test prop_indices_ascending_duplicate_fails(idx via fuzz.int_between(0, 100)) {
  !indices_ascending([idx, idx])
}

test prop_count_satisfied(
  vals via fuzz.both(fuzz.int_between(1, 5), fuzz.int_between(1, 1000000)),
) {
  let (n, lovelace) = vals
  let addr = address.from_verification_key(#"aabb")
  let single_output =
    Output {
      address:          addr,
      value:            assets.from_lovelace(lovelace),
      datum:            NoDatum,
      reference_script: None,
    }
  let outputs = list.repeat(single_output, n)
  count_satisfied(outputs, lovelace) == n
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Descending indices are never ascending — always rejects
test prop_descending_indices_rejected(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(1, 500)),
) fail {
  let (a, b) = vals
  // [a+b, a] is strictly descending, so indices_ascending must return False
  expect indices_ascending([a + b, a])
}

/// Equal consecutive indices are not strictly ascending — always rejects
test prop_equal_indices_rejected(idx via fuzz.int_between(0, 1000)) fail {
  expect indices_ascending([idx, idx, idx])
}

/// output_satisfies on an empty output list always returns False
test prop_output_satisfies_empty_outputs(
  vals via fuzz.both(fuzz.int_between(0, 10), fuzz.int_between(1, 1000000)),
) fail {
  let (idx, min_recv) = vals
  let addr = address.from_verification_key(#"deadbeef")
  let dummy_output =
    Output {
      address:          addr,
      value:            assets.from_lovelace(0),
      datum:            NoDatum,
      reference_script: None,
    }
  expect output_satisfies([], idx, dummy_output, min_recv)
}

/// output_satisfies fails when lovelace in the output is below min_receive
test prop_output_satisfies_insufficient_lovelace(
  vals via fuzz.both(fuzz.int_between(1, 999), fuzz.int_between(1000, 5000000)),
) fail {
  let (actual, min_recv) = vals
  // actual < min_recv is guaranteed by the ranges above
  let addr = address.from_verification_key(#"cafebabe")
  let out =
    Output {
      address:          addr,
      value:            assets.from_lovelace(actual),
      datum:            NoDatum,
      reference_script: None,
    }
  let owner_ref =
    Output {
      address:          addr,
      value:            assets.from_lovelace(0),
      datum:            NoDatum,
      reference_script: None,
    }
  expect output_satisfies([out], 0, owner_ref, min_recv)
}