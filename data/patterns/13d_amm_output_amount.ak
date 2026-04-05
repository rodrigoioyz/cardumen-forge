
use aiken/collection/list
use aiken/fuzz
use aiken/option
use cardano/address
use cardano/assets.{lovelace_of}
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}
  use cardano/address as addr
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

// ── Negative / fail tests ────────────────────────────────────────────────────

// invariant_holds must reject swaps that drain the pool below k.
// If new_a = 1 and new_b = 1 while old reserves are large, k collapses.
test prop_invariant_rejects_drained_pool(
  old_r via fuzz.int_between(1000, 1000000),
) fail {
  // 1 * 1 * 1_000_000 = 1_000_000
  // old_r * old_r * 994_009 is huge — invariant is violated
  expect invariant_holds(old_r, old_r, 1, 1)
}

// invariant_holds must reject when one side is zeroed out entirely.
test prop_invariant_rejects_zero_new_reserve(
  vals via fuzz.both(fuzz.int_between(2, 100000), fuzz.int_between(2, 100000)),
) fail {
  let (old_a, old_b) = vals
  // new_b = 0 makes product 0, always less than positive old product
  expect invariant_holds(old_a, old_b, old_a, 0)
}

// invariant_holds must reject a swap where new reserves are both strictly
// smaller than old reserves by a large factor (reserves halved → k quarters).
test prop_invariant_rejects_halved_reserves(
  r via fuzz.int_between(1000, 500000),
) fail {
  // (r/2) * (r/2) * 1_000_000 = r^2/4 * 1_000_000
  // old: r * r * 994_009 = r^2 * 994_009
  // ratio needed: 1_000_000/4 = 250_000 < 994_009 → always fails
  let half = r / 2
  expect invariant_holds(r, r, half, half)
}

// pool_output_reserves must return None (not Some) when outputs list is empty,
// so wrapping with expect on a None would fail at runtime.
test prop_no_outputs_gives_none() fail {
  let dummy_addr =
    addr.from_verification_key(#"deadbeefdeadbeefdeadbeefdeadbeef")
  expect Some(_) = pool_output_reserves([], dummy_addr)
}