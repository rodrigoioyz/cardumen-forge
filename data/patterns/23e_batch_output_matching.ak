use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/transaction.{NoDatum, Output}

/// Each order in the batch must have a corresponding output with >= required lovelace
fn all_orders_filled(
  outputs:           List<Output>,
  required_lovelace: Int,
  order_count:       Int,
) -> Bool {
  let filled = list.foldl(
    outputs,
    0,
    fn(o, acc) {
      if assets.lovelace_of(o.value) >= required_lovelace {
        acc + 1
      } else {
        acc
      }
    },
  )
  filled >= order_count
}

fn make_output(lovelace: Int) -> Output {
  Output {
    address:          address.from_verification_key(#"aabb"),
    value:            assets.from_lovelace(lovelace),
    datum:            NoDatum,
    reference_script: None,
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_sufficient_outputs_accepted(
  n via fuzz.int_between(1, 5),
) {
  let outputs = list.map(list.range(0, n - 1), fn(_) { make_output(2_000_000) })
  all_orders_filled(outputs, 1_000_000, n)
}

test prop_insufficient_outputs_rejected(
  n via fuzz.int_between(1, 5),
) {
  let outputs = list.map(list.range(0, n - 1), fn(_) { make_output(500_000) })
  !all_orders_filled(outputs, 1_000_000, n)
}

test prop_empty_outputs_zero_orders_ok() {
  all_orders_filled([], 1_000_000, 0)
}

test prop_make_output_has_correct_lovelace(
  lovelace via fuzz.int_between(1_000_000, 10_000_000),
) {
  let out = make_output(lovelace)
  assets.lovelace_of(out.value) == lovelace
}
