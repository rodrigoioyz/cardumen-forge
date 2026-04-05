use aiken/collection/list
use aiken/fuzz
use cardano/transaction.{InlineDatum, Input, OutputReference, Transaction}

pub type OracleDatum {
  price: Int,
}

pub type WindowDatum {
  oracle_ref: OutputReference,
  min_price:  Int,
  max_price:  Int,
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

/// Oracle price must fall within [min_price, max_price] window
fn price_in_window(price: Int, lo: Int, hi: Int) -> Bool {
  price >= lo && price <= hi
}

validator oracle_price_window {
  spend(
    datum: Option<WindowDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when get_oracle_price(self.reference_inputs, d.oracle_ref) is {
      Some(oracle_price) -> price_in_window(oracle_price, d.min_price, d.max_price)
      None -> False
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_price_window_empty_none() {
  let ref =
    OutputReference { transaction_id: #"aabbccdd", output_index: 0 }
  get_oracle_price([], ref) == None
}

test prop_price_in_window_ok(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(1, 50)),
) {
  let (hi, lo) = vals
  let price = lo
  price_in_window(price, lo, hi + lo)
}

test prop_price_below_min_fails(
  vals via fuzz.both(fuzz.int_between(10, 100), fuzz.int_between(1, 9)),
) {
  let (lo, price) = vals
  !price_in_window(price, lo, lo + 50)
}

test prop_price_above_max_fails(
  vals via fuzz.both(fuzz.int_between(1, 50), fuzz.int_between(51, 100)),
) {
  let (max_price, price) = vals
  !price_in_window(price, 1, max_price)
}
