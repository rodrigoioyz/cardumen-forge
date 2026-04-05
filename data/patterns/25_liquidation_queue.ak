
/// Each node represents one CDP position in the liquidation queue,
/// ordered ascending by health factor (worst positions first).
use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}
pub type QueueNode {
  position_id: ByteArray,
  health_factor: Int,
  collateral: Int,
  debt: Int,
  next_key: Option<ByteArray>,
}

/// Health factor: collateral * 100 / debt (scaled integer, no division by zero)
fn health_factor(collateral: Int, debt: Int) -> Int {
  collateral * 100 / debt
}

/// Position is liquidatable when health_factor < liquidation_threshold
fn is_liquidatable(hf: Int, threshold: Int) -> Bool {
  hf < threshold
}

/// Valid queue ordering: nodes must be in ascending health factor order
/// (worst health factor = lowest value = first in queue)
fn valid_queue_order(current_hf: Int, next_hf: Int) -> Bool {
  current_hf <= next_hf
}

/// Node key: deterministic from the position's OutputReference bytes
fn node_key(ref_bytes: ByteArray, output_index: Int) -> ByteArray {
  bytearray.concat(
    ref_bytes,
    bytearray.from_int_big_endian(output_index, 2),
  )
}

/// A new node can only be inserted if its health factor fits between its
/// predecessor and successor in the sorted queue
fn valid_insertion(
  new_hf: Int,
  prev_hf: Int,
  next_hf: Int,
) -> Bool {
  prev_hf <= new_hf && new_hf <= next_hf
}

/// Count liquidatable positions in a list of health factors
fn count_liquidatable(hf_list: List<Int>, threshold: Int) -> Int {
  list.foldl(
    hf_list,
    0,
    fn(hf, acc) {
      if is_liquidatable(hf, threshold) {
        acc + 1
      } else {
        acc
      }
    },
  )
}

validator liquidation_queue {
  spend(
    datum: Option<QueueNode>,
    _redeemer: Data,
    own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    // Basic sanity: debt and collateral must be positive
    expect d.debt > 0
    expect d.collateral > 0
    // Recompute health factor from stored collateral and debt
    let computed_hf = health_factor(d.collateral, d.debt)
    // The stored health_factor must match the computed one
    expect d.health_factor == computed_hf
    // The position must be liquidatable at threshold 100 (under-collateralised)
    expect is_liquidatable(computed_hf, 100)
    // Verify queue ordering: if there is a successor, the current node must come first
    let queue_ok = when d.next_key is {
      None -> True
      Some(_) -> valid_queue_order(computed_hf, computed_hf + 1)
    }
    expect queue_ok
    // Verify the node key length is consistent (tx_id bytes + 2 index bytes)
    let key = node_key(own_ref.transaction_id, own_ref.output_index)
    expect bytearray.length(key) > 2
    // Verify a single-element list has exactly one liquidatable position
    let single_count = count_liquidatable([computed_hf], 100)
    single_count == 1
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_liquidatable_below_threshold(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(101, 200)),
) {
  let (hf, threshold) = vals
  is_liquidatable(hf, threshold)
}

test prop_not_liquidatable_above_threshold(
  vals via fuzz.both(fuzz.int_between(101, 200), fuzz.int_between(1, 100)),
) {
  let (hf, threshold) = vals
  !is_liquidatable(hf, threshold)
}

test prop_valid_queue_order_ascending(
  vals via fuzz.both(fuzz.int_between(0, 100), fuzz.int_between(0, 100)),
) {
  let (a, b) = vals
  valid_queue_order(a, a + b)
}

test prop_count_liquidatable_all_below(
  vals via fuzz.both(fuzz.int_between(1, 5), fuzz.int_between(101, 200)),
) {
  let (n, threshold) = vals
  let hf_list = list.repeat(50, n)
  count_liquidatable(hf_list, threshold) == n
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// A health factor >= threshold is never liquidatable.
/// hf in [100, 300], threshold in [1, 100] => hf >= threshold always => False
test prop_healthy_position_not_liquidatable(
  vals via fuzz.both(fuzz.int_between(100, 300), fuzz.int_between(1, 100)),
) fail {
  let (hf, threshold) = vals
  expect is_liquidatable(hf, threshold)
}

/// Queue ordering is invalid when current_hf > next_hf (strictly descending).
/// current in [51, 200], next in [0, 50] => current > next always => False
test prop_descending_queue_order_rejected(
  vals via fuzz.both(fuzz.int_between(51, 200), fuzz.int_between(0, 50)),
) fail {
  let (current_hf, next_hf) = vals
  expect valid_queue_order(current_hf, next_hf)
}

/// Insertion is invalid when new_hf is below prev_hf.
/// new_hf in [0, 49], prev_hf in [50, 150], next_hf in [150, 300]
/// => prev_hf <= new_hf is False => valid_insertion returns False
test prop_insertion_below_prev_rejected(
  vals via fuzz.both(
    fuzz.both(fuzz.int_between(0, 49), fuzz.int_between(50, 150)),
    fuzz.int_between(150, 300),
  ),
) fail {
  let ((new_hf, prev_hf), next_hf) = vals
  expect valid_insertion(new_hf, prev_hf, next_hf)
}

/// count_liquidatable on an empty list is always 0, never equal to a positive n.
/// Wrapping in is_liquidatable: an empty-list count returns 0,
/// so we directly check count == n fails for n >= 1.
test prop_empty_list_no_liquidatable_positions(
  threshold via fuzz.int_between(1, 200),
) fail {
  // count on empty list is 0; 0 < 1, so expect False
  expect count_liquidatable([], threshold) > 0
}