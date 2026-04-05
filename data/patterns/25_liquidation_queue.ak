use aiken/collection/list
use aiken/fuzz
use aiken/primitive/bytearray
use cardano/fuzz as cfuzz
use cardano/transaction.{OutputReference, Transaction}

/// Each node represents one CDP position in the liquidation queue,
/// ordered ascending by health factor (worst positions first).
pub type QueueNode {
  position_id:   ByteArray,
  health_factor: Int,
  collateral:    Int,
  debt:          Int,
  next_key:      Option<ByteArray>,
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
  new_hf:   Int,
  prev_hf:  Int,
  next_hf:  Int,
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
    _own_ref: OutputReference,
    _self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    d.debt > 0 && d.collateral > 0
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
