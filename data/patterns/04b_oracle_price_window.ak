
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Price strictly below the window lower bound must always be rejected.
test prop_fail_price_below_lo(
  vals via fuzz.both(fuzz.int_between(10, 200), fuzz.int_between(1, 9)),
) fail {
  let (lo, price) = vals
  // price in [1,9], lo in [10,200] → price < lo → price_in_window returns False
  expect price_in_window(price, lo, lo + 100)
}

/// Price strictly above the window upper bound must always be rejected.
test prop_fail_price_above_hi(
  vals via fuzz.both(fuzz.int_between(1, 50), fuzz.int_between(51, 200)),
) fail {
  let (hi, price) = vals
  // price in [51,200], hi in [1,50] → price > hi → price_in_window returns False
  expect price_in_window(price, 1, hi)
}

/// An inverted window (lo > hi) always rejects any price.
test prop_fail_inverted_window(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(101, 300)),
) fail {
  let (price, lo) = vals
  // lo in [101,300], hi = lo - 1 < lo → window is empty → always False
  expect price_in_window(price, lo, lo - 1)
}

/// Zero price is always below a strictly positive lower bound.
test prop_fail_zero_price_positive_window(
  lo via fuzz.int_between(1, 500),
) fail {
  // price = 0, lo >= 1 → 0 < lo → price_in_window returns False
  expect price_in_window(0, lo, lo + 100)
}