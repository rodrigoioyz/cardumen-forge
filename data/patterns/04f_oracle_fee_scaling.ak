use aiken/collection/list
use aiken/fuzz
use cardano/transaction.{InlineDatum, Input, OutputReference, Transaction}

pub type OracleDatum {
  price: Int,
}

pub type FeeScaleDatum {
  oracle_ref: OutputReference,
  base_fee:   Int,
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

/// Fee scales proportionally: base_fee * price / 1000
fn scale_fee(base_fee: Int, price: Int) -> Int {
  base_fee * price / 1000
}

/// Redeemer is the fee paid; must be >= scaled fee
validator oracle_fee_scaling {
  spend(
    datum: Option<FeeScaleDatum>,
    redeemer: Int,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when get_oracle_price(self.reference_inputs, d.oracle_ref) is {
      Some(oracle_price) -> redeemer >= scale_fee(d.base_fee, oracle_price)
      None -> False
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_fee_scaling_empty_none() {
  let ref =
    OutputReference { transaction_id: #"aabbccdd", output_index: 0 }
  get_oracle_price([], ref) == None
}

test prop_scale_fee_zero_price(base via fuzz.int_between(1, 1000)) {
  scale_fee(base, 0) == 0
}

test prop_scale_fee_grows_with_price(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(1001, 2000)),
) {
  let (base, price) = vals
  scale_fee(base, price) >= base
}

test prop_scale_fee_non_negative(
  vals via fuzz.both(fuzz.int_between(0, 1000), fuzz.int_between(0, 1000)),
) {
  let (base, price) = vals
  scale_fee(base, price) >= 0
}
