
/// LP minting is capped at a protocol-defined maximum total supply
use aiken/fuzz
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction, InlineDatum}
fn within_lp_cap(current_total_lp: Int, new_lp: Int, max_lp: Int) -> Bool {
  current_total_lp + new_lp <= max_lp
}

/// Compute new LP for deposit (proportional to smaller side)
fn lp_for_deposit(
  input_a:   Int,
  input_b:   Int,
  reserve_a: Int,
  reserve_b: Int,
  total_lp:  Int,
) -> Int {
  let lp_a = input_a * total_lp / reserve_a
  let lp_b = input_b * total_lp / reserve_b
  if lp_a <= lp_b { lp_a } else { lp_b }
}

/// Deposit is allowed only if resulting total_lp stays under cap
fn deposit_allowed(
  input_a:       Int,
  input_b:       Int,
  reserve_a:     Int,
  reserve_b:     Int,
  current_total: Int,
  max_lp:        Int,
) -> Bool {
  let new_lp = lp_for_deposit(input_a, input_b, reserve_a, reserve_b, current_total)
  within_lp_cap(current_total, new_lp, max_lp)
}

// ── Datum / Redeemer types ───────────────────────────────────────────────────

pub type PoolDatum {
  reserve_a:     Int,
  reserve_b:     Int,
  current_total: Int,
  max_lp:        Int,
}

pub type DepositRedeemer {
  input_a: Int,
  input_b: Int,
}

// ── Validator ────────────────────────────────────────────────────────────────

validator lp_cap_deposit {
  spend(
    datum: Option<PoolDatum>,
    redeemer: DepositRedeemer,
    _output_reference: Data,
    _self: Transaction,
  ) {
    when datum is {
      None -> False
      Some(pool) -> {
        let DepositRedeemer { input_a, input_b } = redeemer
        expect input_a > 0
        expect input_b > 0
        expect pool.reserve_a > 0
        expect pool.reserve_b > 0
        deposit_allowed(
          input_a,
          input_b,
          pool.reserve_a,
          pool.reserve_b,
          pool.current_total,
          pool.max_lp,
        )
      }
    }
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_within_cap_exact_boundary(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(501, 1000)),
) {
  let (current, max_lp) = vals
  within_lp_cap(current, 0, max_lp)
}

test prop_exceeds_cap_rejected(
  max_lp via fuzz.int_between(1, 999),
) {
  !within_lp_cap(max_lp, 1, max_lp)
}

test prop_deposit_within_large_cap(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (input, reserve) = vals
  deposit_allowed(input, input, reserve, reserve, 1000, 1_000_000_000)
}

test prop_deposit_rejected_at_cap(
  reserve via fuzz.int_at_least(1),
) {
  // current == max_lp means no new LP can be minted
  !deposit_allowed(reserve, reserve, reserve, reserve, 1000, 1000)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// within_lp_cap must reject when current already equals max_lp and new_lp > 0
test prop_fail_within_lp_cap_already_full(
  new_lp via fuzz.int_between(1, 1000),
) fail {
  // current_total_lp == max_lp, so current + new_lp > max_lp always
  expect within_lp_cap(1000, new_lp, 1000)
}

/// within_lp_cap must reject when current + new_lp exceeds max_lp
test prop_fail_within_lp_cap_overflow(
  vals via fuzz.both(fuzz.int_between(501, 1000), fuzz.int_between(501, 1000)),
) fail {
  let (current, new_lp) = vals
  // current >= 501, new_lp >= 501 → sum >= 1002 > 1000 = max_lp
  expect within_lp_cap(current, new_lp, 1000)
}

/// deposit_allowed must reject when current_total already equals max_lp
/// (any positive deposit produces new_lp >= 1, exceeding the cap)
test prop_fail_deposit_at_exact_cap(
  input via fuzz.int_between(1, 500),
) fail {
  // reserve == total_lp == max_lp, so lp_for_deposit >= 1 and cap is already hit
  expect deposit_allowed(input, input, 1000, 1000, 1000, 1000)
}

/// deposit_allowed must reject when current_total far exceeds max_lp
test prop_fail_deposit_current_exceeds_max() fail {
  // current_total (2000) > max_lp (1000): cap already blown, no deposit possible
  expect deposit_allowed(1, 1, 1000, 1000, 2000, 1000)
}