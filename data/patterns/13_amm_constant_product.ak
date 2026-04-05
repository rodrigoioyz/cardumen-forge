
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

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Both new reserves are zero → product is 0, invariant must fail for any
/// positive old reserves.
test prop_invariant_fails_both_outputs_zero(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) fail {
  let (old_a, old_b) = vals
  expect invariant_holds(old_a, old_b, 0, 0)
}

/// One side of the new reserves is zero → product collapses to 0, invariant
/// must reject regardless of the other side.
test prop_invariant_fails_new_a_zero(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) fail {
  let (old_r, new_b) = vals
  // new_a = 0  →  0 * new_b * 1_000_000 = 0 < old_r*old_r*994_009 (positive)
  expect invariant_holds(old_r, old_r, 0, new_b)
}

/// Draining almost all of one reserve while keeping the other tiny.
/// new_a = 1, new_b = 1  →  product = 1, which is tiny compared to
/// large old reserves whose product is old_a * old_b >= 10_000.
test prop_invariant_fails_near_total_drain(
  vals via fuzz.both(fuzz.int_at_least(100), fuzz.int_at_least(100)),
) fail {
  let (old_a, old_b) = vals
  // 1 * 1 * 1_000_000 = 1_000_000  vs  old_a * old_b * 994_009 >= 100*100*994_009 = 9_940_090_000
  expect invariant_holds(old_a, old_b, 1, 1)
}

/// Shrinking reserves by a large factor guarantees the invariant breaks.
/// new_a = 1, new_b = old_b  but old_a is huge (>= 1_000_000).
/// new_a * new_b * 1_000_000 = old_b * 1_000_000
/// old_a * old_b * 994_009  >= 1_000_000 * old_b * 994_009  >> old_b * 1_000_000
test prop_invariant_fails_massive_a_drain(
  vals via fuzz.both(fuzz.int_at_least(1000000), fuzz.int_at_least(1)),
) fail {
  let (old_a, old_b) = vals
  expect invariant_holds(old_a, old_b, 1, old_b)
}