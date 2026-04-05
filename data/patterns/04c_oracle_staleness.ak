
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// age = max_age + 1 guarantees current_slot - posted_slot > max_age,
/// so is_fresh must return False for every input in this range.
test prop_stale_oracle_rejected(
  vals via fuzz.both(
    fuzz.int_between(0, 10),
    fuzz.int_between(100, 200),
  ),
) fail {
  let (max_age, age) = vals
  // posted_slot = current_slot - age, with age > max_age always
  // current_slot fixed at 500 so posted_slot is always positive
  expect is_fresh(500 - age, 500, max_age)
}

/// max_age = -1 with any non-negative age means always stale.
test prop_negative_max_age_rejected(
  age via fuzz.int_between(0, 1000),
) fail {
  // current_slot - posted_slot = age >= 0 > -1
  expect is_fresh(1000 - age, 1000, -1)
}

/// current_slot far behind posted_slot with max_age = 0 is always stale
/// (current_slot - posted_slot is a large negative? No — we set
/// posted_slot > current_slot so diff < 0, but we want > max_age.)
/// Instead: posted_slot = 0, current_slot = age, max_age = age - 1
/// so diff = age > age - 1 — always stale for age >= 1.
test prop_exceeded_by_one_rejected(
  age via fuzz.int_between(1, 500),
) fail {
  expect is_fresh(0, age, age - 1)
}

/// Zero max_age with any strictly positive staleness is always rejected.
test prop_zero_max_age_any_lag_rejected(
  lag via fuzz.int_between(1, 1000),
) fail {
  // current_slot - posted_slot = lag > 0 = max_age
  expect is_fresh(0, lag, 0)
}