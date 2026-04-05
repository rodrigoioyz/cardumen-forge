use aiken/collection/list
use aiken/fuzz
use cardano/transaction.{InlineDatum, Input, OutputReference, Transaction}

pub type OracleDatum {
  price: Int,
}

pub type DiscountDatum {
  oracle_ref:       OutputReference,
  discount_percent: Int,
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

/// Discounted floor: price * (100 - pct) / 100
fn discounted_floor(price: Int, pct: Int) -> Int {
  price * (100 - pct) / 100
}

/// Redeemer is the amount paid; must be >= discounted oracle price
validator oracle_discount {
  spend(
    datum: Option<DiscountDatum>,
    redeemer: Int,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when get_oracle_price(self.reference_inputs, d.oracle_ref) is {
      Some(oracle_price) ->
        redeemer >= discounted_floor(oracle_price, d.discount_percent)
      None -> False
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_oracle_discount_empty_none() {
  let ref =
    OutputReference { transaction_id: #"aabbccdd", output_index: 0 }
  get_oracle_price([], ref) == None
}

test prop_discounted_floor_zero_pct(price via fuzz.int_between(1, 1000)) {
  discounted_floor(price, 0) == price
}

test prop_discounted_floor_less_than_price(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(1, 50)),
) {
  let (price, pct) = vals
  discounted_floor(price, pct) < price
}

test prop_discounted_floor_non_negative(
  vals via fuzz.both(fuzz.int_between(0, 1000), fuzz.int_between(0, 100)),
) {
  let (price, pct) = vals
  discounted_floor(price, pct) >= 0
}
