
use aiken/collection/list
use aiken/fuzz
use aiken/option
use cardano/address
use cardano/assets.{lovelace_of}
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}
pub type PoolDatum {
  reserve_a:      Int,
  reserve_b:      Int,
  lp_policy:      ByteArray,
  fee_multiplier: Int,
}

/// Generalised constant product: new_a * new_b * 1_000_000 >= old_a * old_b * fee_multiplier
/// fee_multiplier examples: 994009 (0.3%), 998001 (0.1%), 980100 (1%)
fn invariant_with_fee(
  old_a:          Int,
  old_b:          Int,
  new_a:          Int,
  new_b:          Int,
  fee_multiplier: Int,
) -> Bool {
  new_a * new_b * 1000000 >= old_a * old_b * fee_multiplier
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

validator amm_fee_tier {
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
        invariant_with_fee(
          d.reserve_a,
          d.reserve_b,
          new_a,
          new_b,
          d.fee_multiplier,
        )
      None -> False
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_fee_tier_equal_reserves(r via fuzz.int_at_least(1)) {
  invariant_with_fee(r, r, r, r, 994009)
}

test prop_fee_tier_lower_fee_easier(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (a, b) = vals
  // If invariant holds at 0.3% fee, it holds at 0.1% fee (lower multiplier)
  let holds_03 = invariant_with_fee(a, b, a, b, 994009)
  let holds_01 = invariant_with_fee(a, b, a, b, 998001)
  holds_03 == holds_01
}

test prop_fee_tier_zero_output_fails(r via fuzz.int_at_least(1)) {
  !invariant_with_fee(r, r, 0, r, 994009)
}

test prop_fee_tier_grows_holds(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (old, extra) = vals
  invariant_with_fee(old, old, old + extra, old + extra, 994009)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// Both outputs at zero must always violate the invariant for any positive reserves.
test prop_both_outputs_zero_fails(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) fail {
  let (old_a, old_b) = vals
  // new_a=0, new_b=0 => 0 * 0 * 1_000_000 = 0 < old_a * old_b * fee_multiplier (> 0)
  expect invariant_with_fee(old_a, old_b, 0, 0, 994009)
}

// Draining one side to zero always breaks the invariant (old reserves positive).
test prop_one_side_drained_fails(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) fail {
  let (old_a, old_b) = vals
  // new_b=0 => product=0, invariant cannot hold for positive old reserves
  expect invariant_with_fee(old_a, old_b, old_a, 0, 994009)
}

// A fee_multiplier strictly greater than 1_000_000 means the pool must grow —
// equal reserves therefore always fail.
test prop_fee_multiplier_above_million_fails(
  vals via fuzz.both(
    fuzz.int_at_least(1),
    fuzz.int_between(1000001, 2000000),
  ),
) fail {
  let (r, fm) = vals
  // r * r * 1_000_000 < r * r * fm  when fm > 1_000_000
  expect invariant_with_fee(r, r, r, r, fm)
}

// Reserves that shrink drastically (new < old / 2) always break the invariant
// because (old/2)^2 * 1_000_000 < old^2 * 994009 for any old >= 2.
test prop_halved_reserves_fail(
  old via fuzz.int_between(2, 1000000),
) fail {
  let half = old / 2
  // half * half * 1_000_000 = old^2/4 * 1_000_000 < old^2 * 994009
  expect invariant_with_fee(old, old, half, half, 994009)
}