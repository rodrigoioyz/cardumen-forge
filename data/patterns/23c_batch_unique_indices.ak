
/// All indices in the list are unique (no duplicates)
use aiken/collection/list
use aiken/fuzz
use cardano/transaction.{Transaction}
fn all_unique(indices: List<Int>) -> Bool {
  when indices is {
    []           -> True
    [head, ..tail] ->
      !list.has(tail, head) && all_unique(tail)
  }
}

/// Indices are within bounds [0, max_idx)
fn all_in_bounds(indices: List<Int>, max_idx: Int) -> Bool {
  list.all(indices, fn(i) { i >= 0 && i < max_idx })
}

/// Valid index set: unique and in bounds
fn valid_index_set(indices: List<Int>, max_idx: Int) -> Bool {
  all_unique(indices) && all_in_bounds(indices, max_idx)
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_empty_indices_unique() {
  all_unique([])
}

test prop_single_index_unique(
  i via fuzz.int_between(0, 100),
) {
  all_unique([i])
}

test prop_two_same_not_unique(
  i via fuzz.int_between(0, 100),
) {
  !all_unique([i, i])
}

test prop_valid_index_set_accepted(
  max_idx via fuzz.int_between(3, 10),
) {
  valid_index_set([0, 1, 2], max_idx)
}

// ── Redeemer type ────────────────────────────────────────────────────────────

pub type BatchRedeemer {
  indices: List<Int>,
  max_idx: Int,
}

// ── Validator ────────────────────────────────────────────────────────────────

validator batch_unique_indices {
  spend(
    _datum: Option<Data>,
    redeemer: BatchRedeemer,
    _output_ref: Data,
    _self: Transaction,
  ) {
    let BatchRedeemer { indices, max_idx } = redeemer
    expect max_idx > 0
    expect list.length(indices) > 0
    valid_index_set(indices, max_idx)
  }

  else(_) {
    fail
  }
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Duplicate indices always fail all_unique
test prop_duplicate_indices_rejected(
  i via fuzz.int_between(0, 200),
) fail {
  expect all_unique([i, i])
}

/// An index equal to max_idx is out of bounds (must be < max_idx)
test prop_index_at_max_out_of_bounds(
  max_idx via fuzz.int_between(1, 100),
) fail {
  expect all_in_bounds([max_idx], max_idx)
}

/// Negative indices are always out of bounds for any positive max_idx
test prop_negative_index_out_of_bounds(
  vals via fuzz.both(fuzz.int_between(-500, -1), fuzz.int_between(1, 100)),
) fail {
  let (neg_idx, max_idx) = vals
  expect all_in_bounds([neg_idx], max_idx)
}

/// Duplicate indices make valid_index_set fail even when in bounds
test prop_duplicate_indices_invalid_set(
  vals via fuzz.both(fuzz.int_between(0, 9), fuzz.int_between(10, 20)),
) fail {
  let (i, max_idx) = vals
  expect valid_index_set([i, i], max_idx)
}