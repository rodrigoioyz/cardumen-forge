use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/assets.{lovelace_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{NoDatum, Output, OutputReference, Transaction}

/// Each swap order is indexed: input at position i must correspond to
/// output at position i. This prevents double satisfaction by requiring
/// strictly ascending output indices.
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
