use aiken/collection/list
use aiken/fuzz

/// All indices in the list are unique (no duplicates)
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
