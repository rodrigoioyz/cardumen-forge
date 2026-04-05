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
