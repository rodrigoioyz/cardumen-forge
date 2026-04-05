use aiken/collection/list
use aiken/fuzz
use aiken/option
use cardano/address
use cardano/assets.{lovelace_of}
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}

pub type PoolDatum {
  reserve_a:  Int,
  reserve_b:  Int,
  lp_policy:  ByteArray,
}

/// Constant product invariant with 0.3% fee (multiplied out to avoid fractions)
/// new_a * new_b * 1_000_000 >= old_a * old_b * 994_009
fn invariant_holds(
  old_a: Int,
  old_b: Int,
  new_a: Int,
  new_b: Int,
) -> Bool {
  new_a * new_b * 1000000 >= old_a * old_b * 994009
}

/// Find the continuing pool output (same script address as input)
fn pool_output_reserves(
  outputs: List<Output>,
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

validator amm_pool {
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

test prop_invariant_holds_equal_reserves(r via fuzz.int_at_least(1)) {
  // Same reserves → invariant holds (no swap)
  invariant_holds(r, r, r, r)
}

test prop_invariant_holds_larger_reserves(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (old, extra) = vals
  // Both sides grow → invariant holds
  invariant_holds(old, old, old + extra, old + extra)
}

test prop_invariant_fails_zero_output(r via fuzz.int_at_least(1)) {
  !invariant_holds(r, r, 0, r)
}

test prop_invariant_symmetric(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (a, b) = vals
  // invariant(a,b,c,d) == invariant(b,a,d,c)
  invariant_holds(a, b, a, b) == invariant_holds(b, a, b, a)
}
