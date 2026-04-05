
/// Each order in the batch must have a corresponding output with >= required lovelace
use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets
use cardano/transaction.{NoDatum, Output}
fn all_orders_filled(
  outputs: List<Output>,
  required_lovelace: Int,
  order_count: Int,
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
    address: address.from_verification_key(#"aabb"),
    value: assets.from_lovelace(lovelace),
    datum: NoDatum,
    reference_script: None,
  }
}

// ── Validator ─────────────────────────────────────────────────────────────────

pub type BatchDatum {
  required_lovelace: Int,
  order_count: Int,
}

pub type BatchRedeemer {
  Fill
}

validator batch_output_matching {
  spend(
    datum: Option<BatchDatum>,
    redeemer: BatchRedeemer,
    _own_ref: Data,
    self: transaction.Transaction,
  ) {
    expect Some(d) = datum
    expect Fill = redeemer
    all_orders_filled(self.outputs, d.required_lovelace, d.order_count)
  }

  else(_) {
    fail
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

// ── Negative (fail) property tests ───────────────────────────────────────────

// Empty output list can never satisfy a positive order_count
test prop_empty_outputs_nonzero_orders_rejected(
  order_count via fuzz.int_between(1, 20),
) fail {
  expect all_orders_filled([], 1_000_000, order_count)
}

// Outputs with lovelace below required never count, so filled=0 < order_count
test prop_all_underfunded_outputs_rejected(
  params via fuzz.both(fuzz.int_between(1, 5), fuzz.int_between(1, 499_999)),
) fail {
  let (n, low_lovelace) = params
  let outputs =
    list.map(list.range(0, n - 1), fn(_) { make_output(low_lovelace) })
  // required=500_000 > low_lovelace for every draw, so none qualify
  expect all_orders_filled(outputs, 500_000, n)
}

// Fewer outputs than required orders: even if all outputs qualify, filled < order_count
test prop_fewer_outputs_than_orders_rejected(
  params via fuzz.both(fuzz.int_between(1, 4), fuzz.int_between(5, 10)),
) fail {
  let (output_count, order_count) = params
  // output_count < order_count always (1..4 vs 5..10)
  let outputs =
    list.map(
      list.range(0, output_count - 1),
      fn(_) { make_output(2_000_000) },
    )
  expect all_orders_filled(outputs, 1_000_000, order_count)
}

// Single zero-lovelace output against any positive required amount and order_count>=1
test prop_zero_lovelace_output_rejected(
  required via fuzz.int_between(1, 10_000_000),
) fail {
  let outputs = [make_output(0)]
  // lovelace_of(output)=0 < required>=1, so filled=0 < order_count=1
  expect all_orders_filled(outputs, required, 1)
}