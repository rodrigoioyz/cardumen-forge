
use aiken/collection/list
use aiken/fuzz
use aiken/option
use cardano/address
use cardano/assets.{lovelace_of}
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}
pub type PoolDatum {
  reserve_a:    Int,
  reserve_b:    Int,
  lp_policy:    ByteArray,
  min_reserve:  Int,
}

fn invariant_holds(old_a: Int, old_b: Int, new_a: Int, new_b: Int) -> Bool {
  new_a * new_b * 1000000 >= old_a * old_b * 994009
}

/// Both reserves must stay above the minimum after a swap
fn min_reserves_ok(new_a: Int, new_b: Int, min_reserve: Int) -> Bool {
  new_a >= min_reserve && new_b >= min_reserve
}

fn pool_output_reserves(
  outputs:  List<Output>,
  own_addr: address.Address,
) -> Option<Pair<Int, Int>> {
  list.find_map(
    outputs,
    fn(o) {
      if o.address == own_addr {
        when o.datum is {
          InlineDatum(raw) -> {
            expect d: PoolDatum = raw
            Some(Pair(d.reserve_a, d.reserve_b))
          }
          _ -> None
        }
      } else {
        None
      }
    },
  )
}

validator amm_min_reserves {
  spend(
    datum: Option<PoolDatum>,
    _own_ref: OutputReference,
    _redeemer: Data,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let own_addr = (list.head(self.inputs) |> option.or_else(fail)).output.address
    when pool_output_reserves(self.outputs, own_addr) is {
      Some(Pair(new_a, new_b)) ->
        invariant_holds(d.reserve_a, d.reserve_b, new_a, new_b) && min_reserves_ok(
          new_a,
          new_b,
          d.min_reserve,
        )
      None -> False
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_min_reserves_ok_above(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(0, 100)),
) {
  let (min, extra) = vals
  min_reserves_ok(min + extra, min + extra, min)
}

test prop_min_reserves_ok_exact(min via fuzz.int_at_least(1)) {
  min_reserves_ok(min, min, min)
}

test prop_min_reserves_a_fails(
  vals via fuzz.both(fuzz.int_at_least(2), fuzz.int_at_least(1)),
) {
  let (min, b) = vals
  !min_reserves_ok(min - 1, b + min, min)
}

test prop_invariant_equal(r via fuzz.int_at_least(1)) {
  invariant_holds(r, r, r, r)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

// reserve_a is strictly below min_reserve, reserve_b is at or above —
// min_reserves_ok must return False because new_a < min_reserve
test prop_new_a_below_min_reserves_rejected(
  vals via fuzz.both(fuzz.int_at_least(2), fuzz.int_at_least(1)),
) fail {
  let (min, extra) = vals
  // new_a = min - 1  < min, new_b = min + extra >= min
  expect min_reserves_ok(min - 1, min + extra, min)
}

// reserve_b is strictly below min_reserve, reserve_a is at or above —
// min_reserves_ok must return False because new_b < min_reserve
test prop_new_b_below_min_reserves_rejected(
  vals via fuzz.both(fuzz.int_at_least(2), fuzz.int_at_least(1)),
) fail {
  let (min, extra) = vals
  // new_a = min + extra >= min, new_b = min - 1 < min
  expect min_reserves_ok(min + extra, min - 1, min)
}

// Both reserves are zero while min_reserve is positive —
// min_reserves_ok must return False
test prop_both_zero_reserves_rejected(
  min via fuzz.int_at_least(1),
) fail {
  expect min_reserves_ok(0, 0, min)
}

// invariant_holds must return False when new product is drastically smaller
// than old product (large drain: new reserves are 1 while old are large)
test prop_invariant_violated_large_drain(
  old via fuzz.int_at_least(1000),
) fail {
  // old_a * old_b = old^2, new_a * new_b = 1
  // 1 * 1000000 < old^2 * 994009 for old >= 1000
  expect invariant_holds(old, old, 1, 1)
}