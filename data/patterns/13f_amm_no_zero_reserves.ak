
use aiken/collection/list
use aiken/fuzz
use aiken/option
use cardano/address
use cardano/assets.{lovelace_of}
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}
pub type PoolDatum {
  reserve_a: Int,
  reserve_b: Int,
  lp_policy: ByteArray,
}

fn invariant_holds(old_a: Int, old_b: Int, new_a: Int, new_b: Int) -> Bool {
  new_a * new_b * 1000000 >= old_a * old_b * 994009
}

/// After swap, neither reserve may be zero or negative
fn no_zero_reserves(new_a: Int, new_b: Int) -> Bool {
  new_a > 0 && new_b > 0
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

validator amm_no_zero_reserves {
  spend(
    datum: Option<PoolDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let own_addr = (list.head(self.inputs) |> option.or_else(fail)).output.address
    when pool_output_reserves(self.outputs, own_addr) is {
      Some(Pair(new_a, new_b)) ->
        no_zero_reserves(new_a, new_b) && invariant_holds(
          d.reserve_a,
          d.reserve_b,
          new_a,
          new_b,
        )
      None -> False
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_no_zero_both_positive(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (a, b) = vals
  no_zero_reserves(a, b)
}

test prop_no_zero_a_fails(b via fuzz.int_at_least(1)) {
  !no_zero_reserves(0, b)
}

test prop_no_zero_b_fails(a via fuzz.int_at_least(1)) {
  !no_zero_reserves(a, 0)
}

test prop_invariant_preserves_no_zero(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (r, extra) = vals
  no_zero_reserves(r + extra, r + extra) && invariant_holds(r, r, r + extra, r + extra)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

// new_a == 0 always makes no_zero_reserves return False
test prop_fail_zero_a(
  b via fuzz.int_at_least(1),
) fail {
  expect no_zero_reserves(0, b)
}

// new_b == 0 always makes no_zero_reserves return False
test prop_fail_zero_b(
  a via fuzz.int_at_least(1),
) fail {
  expect no_zero_reserves(a, 0)
}

// both zero always makes no_zero_reserves return False
test prop_fail_both_zero() fail {
  expect no_zero_reserves(0, 0)
}

// negative new_a always makes no_zero_reserves return False
test prop_fail_negative_a(
  vals via fuzz.both(fuzz.int_between(-1000, -1), fuzz.int_at_least(1)),
) fail {
  let (neg_a, b) = vals
  expect no_zero_reserves(neg_a, b)
}