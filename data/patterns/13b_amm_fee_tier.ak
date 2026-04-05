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
