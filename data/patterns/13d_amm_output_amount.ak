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

/// Compute output_b for a given input_a using x*y=k with 0.3% fee
fn compute_output(input_a: Int, reserve_a: Int, reserve_b: Int) -> Int {
  reserve_b * input_a * 997 / (reserve_a * 1000 + input_a * 997)
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

validator amm_output_amount {
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
        invariant_holds(d.reserve_a, d.reserve_b, new_a, new_b)
      None -> False
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_compute_output_positive(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (input, reserve) = vals
  compute_output(input, reserve, reserve) >= 0
}

test prop_compute_output_less_than_reserve(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (input, reserve) = vals
  compute_output(input, reserve, reserve) < reserve
}

test prop_compute_output_grows_with_input(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (reserve, extra) = vals
  compute_output(reserve + extra, reserve, reserve) >= compute_output(
    reserve,
    reserve,
    reserve,
  )
}

test prop_invariant_equal(r via fuzz.int_at_least(1)) {
  invariant_holds(r, r, r, r)
}
