use aiken/collection/list
use aiken/fuzz
use cardano/transaction.{InlineDatum, Input, OutputReference, Transaction}

pub type OracleDatum {
  price: Int,
}

pub type SpendDatum {
  oracle_ref: OutputReference,
  min_price:  Int,
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

/// Redeemer: the amount the user claims to receive
validator oracle_spend {
  spend(
    datum: Option<SpendDatum>,
    redeemer: Int,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when get_oracle_price(self.reference_inputs, d.oracle_ref) is {
      Some(oracle_price) -> oracle_price >= d.min_price && redeemer >= oracle_price
      None -> False
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_get_oracle_price_empty_inputs_none(
  _dummy via fuzz.int(),
) {
  let ref =
    OutputReference {
      transaction_id: #"aabbccdd",
      output_index: 0,
    }
  get_oracle_price([], ref) == None
}
