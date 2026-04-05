
use aiken/collection/list
use aiken/fuzz
use cardano/transaction.{InlineDatum, Input, OutputReference, Transaction}
pub type OracleDatum {
  price: Int,
}

pub type LiqDatum {
  oracle_ref:            OutputReference,
  liquidation_threshold: Int,
}

/// Find oracle price from reference inputs
fn get_oracle_price(
  ref_inputs: List<Input>,
  oracle_ref: OutputReference,
) -> Option<Int> {
  list.find_map(
    ref_inputs,
    fn(inp) {
      if inp.output_reference == oracle_ref {
        when inp.output.datum is {
          InlineDatum(raw) -> {
            expect d: OracleDatum = raw
            Some(d.price)
          }
          _ -> None
        }
      } else {
        None
      }
    },
  )
}

/// Position is liquidatable when oracle price drops below threshold
fn is_liquidatable(oracle_price: Int, threshold: Int) -> Bool {
  oracle_price < threshold
}

validator oracle_liquidation {
  spend(
    datum: Option<LiqDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when get_oracle_price(self.reference_inputs, d.oracle_ref) is {
      Some(oracle_price) ->
        is_liquidatable(oracle_price, d.liquidation_threshold)
      None -> False
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_liquidation_empty_none() {
  let ref =
    OutputReference { transaction_id: #"aabbccdd", output_index: 0 }
  get_oracle_price([], ref) == None
}

test prop_price_below_threshold_liquidatable(
  vals via fuzz.both(fuzz.int_between(1, 50), fuzz.int_between(51, 100)),
) {
  let (price, threshold) = vals
  is_liquidatable(price, threshold)
}

test prop_price_at_threshold_safe(threshold via fuzz.int_between(1, 100)) {
  !is_liquidatable(threshold, threshold)
}

test prop_price_above_threshold_safe(
  vals via fuzz.both(fuzz.int_between(51, 100), fuzz.int_between(1, 50)),
) {
  let (price, threshold) = vals
  !is_liquidatable(price, threshold)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// Price equal to threshold is NOT liquidatable — expect fails because
/// is_liquidatable returns False when price == threshold.
test prop_price_equal_threshold_not_liquidatable(
  threshold via fuzz.int_between(1, 1000),
) fail {
  expect is_liquidatable(threshold, threshold)
}

/// Price strictly above threshold is NOT liquidatable — expect fails because
/// is_liquidatable returns False when price > threshold.
test prop_price_above_threshold_not_liquidatable(
  vals via fuzz.both(fuzz.int_between(51, 1000), fuzz.int_between(1, 50)),
) fail {
  let (price, threshold) = vals
  expect is_liquidatable(price, threshold)
}

/// Zero price with zero threshold is NOT liquidatable — 0 < 0 is False.
test prop_zero_price_zero_threshold_not_liquidatable() fail {
  expect is_liquidatable(0, 0)
}

/// Negative threshold with price equal to that negative threshold is NOT
/// liquidatable — price == threshold means False.
test prop_negative_equal_values_not_liquidatable(
  n via fuzz.int_between(-500, -1),
) fail {
  expect is_liquidatable(n, n)
}