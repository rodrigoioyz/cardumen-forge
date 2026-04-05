use aiken/collection/list
use aiken/fuzz
use cardano/transaction.{InlineDatum, Input, OutputReference, Transaction}

pub type OracleDatum {
  price:      Int,
  posted_slot: Int,
}

pub type FreshDatum {
  oracle_ref:   OutputReference,
  current_slot: Int,
  max_age:      Int,
}

/// Find oracle (price, slot) from reference inputs
fn get_oracle_entry(
  ref_inputs: List<Input>,
  oracle_ref: OutputReference,
) -> Option<(Int, Int)> {
  list.find_map(
    ref_inputs,
    fn(inp) {
      if inp.output_reference == oracle_ref {
        when inp.output.datum is {
          InlineDatum(raw) -> {
            expect d: OracleDatum = raw
            Some((d.price, d.posted_slot))
          }
          _ -> None
        }
      } else {
        None
      }
    },
  )
}

/// Oracle is fresh if current_slot - posted_slot <= max_age
fn is_fresh(posted_slot: Int, current_slot: Int, max_age: Int) -> Bool {
  current_slot - posted_slot <= max_age
}

validator oracle_staleness {
  spend(
    datum: Option<FreshDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when get_oracle_entry(self.reference_inputs, d.oracle_ref) is {
      Some((price, posted_slot)) ->
        price > 0 && is_fresh(posted_slot, d.current_slot, d.max_age)
      None -> False
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_staleness_empty_none() {
  let ref =
    OutputReference { transaction_id: #"aabbccdd", output_index: 0 }
  get_oracle_entry([], ref) == None
}

test prop_fresh_oracle_ok(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(0, 10)),
) {
  let (current, age) = vals
  is_fresh(current - age, current, 10)
}

test prop_stale_oracle_fails(
  vals via fuzz.both(fuzz.int_between(20, 100), fuzz.int_between(11, 50)),
) {
  let (current, age) = vals
  !is_fresh(current - age, current, 10)
}

test prop_same_slot_is_fresh(slot via fuzz.int_between(0, 1000)) {
  is_fresh(slot, slot, 0)
}
