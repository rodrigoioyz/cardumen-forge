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

pub type SwapRedeemer {
  min_output: Int,
}

fn invariant_holds(old_a: Int, old_b: Int, new_a: Int, new_b: Int) -> Bool {
  new_a * new_b * 1000000 >= old_a * old_b * 994009
}

/// Slippage guard: actual output must be at least min_output
fn slippage_ok(old_b: Int, new_b: Int, min_output: Int) -> Bool {
  let output = old_b - new_b
  output >= min_output
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

validator amm_slippage {
  spend(
    datum: Option<PoolDatum>,
    redeemer: SwapRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let own_addr = (list.head(self.inputs) |> option.or_else(fail)).output.address
    when pool_output_reserves(self.outputs, own_addr) is {
      Some(Pair(new_a, new_b)) ->
        invariant_holds(d.reserve_a, d.reserve_b, new_a, new_b) && slippage_ok(
          d.reserve_b,
          new_b,
          redeemer.min_output,
        )
      None -> False
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_slippage_ok_zero_min(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(0, 100)),
) {
  let (old_b, delta) = vals
  slippage_ok(old_b, old_b - delta, 0)
}

test prop_slippage_ok_exact_min(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(1, 100)),
) {
  let (old_b, delta) = vals
  slippage_ok(old_b, old_b - delta, delta)
}

test prop_slippage_fails_min_too_high(
  vals via fuzz.both(fuzz.int_at_least(2), fuzz.int_between(1, 100)),
) {
  let (old_b, delta) = vals
  !slippage_ok(old_b, old_b - delta, delta + 1)
}

test prop_invariant_equal(r via fuzz.int_at_least(1)) {
  invariant_holds(r, r, r, r)
}
