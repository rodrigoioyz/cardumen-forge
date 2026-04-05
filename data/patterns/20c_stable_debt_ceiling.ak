
/// Global debt ceiling: total minted stablecoin must not exceed the cap
use aiken/fuzz
use aiken/collection/list
use cardano/assets
use cardano/transaction.{Transaction}
fn under_debt_ceiling(
  current_supply: Int,
  mint_amount:    Int,
  debt_ceiling:   Int,
) -> Bool {
  mint_amount > 0 && current_supply + mint_amount <= debt_ceiling
}

/// Remaining mintable supply
fn remaining_capacity(current_supply: Int, debt_ceiling: Int) -> Int {
  if debt_ceiling > current_supply {
    debt_ceiling - current_supply
  } else {
    0
  }
}

// ── Validator ────────────────────────────────────────────────────────────────

pub type StableRedeemer {
  current_supply: Int,
  debt_ceiling: Int,
}

validator stable_debt_ceiling {
  mint(redeemer: StableRedeemer, policy_id: ByteArray, self: Transaction) {
    let mint_amount =
      assets.reduce(
        self.mint,
        0,
        fn(policy, _name, qty, acc) {
          if policy == policy_id {
            acc + qty
          } else {
            acc
          }
        },
      )
    let cap = remaining_capacity(redeemer.current_supply, redeemer.debt_ceiling)
    let fits = under_debt_ceiling(redeemer.current_supply, mint_amount, redeemer.debt_ceiling)
    fits && cap >= mint_amount
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_mint_under_ceiling(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(501, 1000)),
) {
  let (supply, ceiling) = vals
  under_debt_ceiling(supply, 1, ceiling)
}

test prop_mint_at_ceiling_rejected(
  ceiling via fuzz.int_between(1, 1000),
) {
  !under_debt_ceiling(ceiling, 1, ceiling)
}

test prop_remaining_capacity_correct(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(501, 1000)),
) {
  let (supply, ceiling) = vals
  remaining_capacity(supply, ceiling) == ceiling - supply
}

test prop_no_capacity_at_ceiling(
  ceiling via fuzz.int_between(1, 1000),
) {
  remaining_capacity(ceiling, ceiling) == 0
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// Minting zero tokens must always be rejected (mint_amount > 0 guard fails)
test prop_zero_mint_rejected(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(501, 1000)),
) fail {
  let (supply, ceiling) = vals
  expect under_debt_ceiling(supply, 0, ceiling)
}

/// Minting a negative amount must always be rejected
test prop_negative_mint_rejected(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(-1000, -1)),
) fail {
  let (supply, mint_amount) = vals
  // ceiling is set high enough that only the sign check matters
  expect under_debt_ceiling(supply, mint_amount, 1000000)
}

/// Minting more than the ceiling allows must be rejected:
/// supply + mint_amount > debt_ceiling when mint_amount > ceiling - supply + 1
test prop_exceeds_ceiling_rejected(
  vals via fuzz.both(fuzz.int_between(0, 499), fuzz.int_between(1, 500)),
) fail {
  let (supply, ceiling) = vals
  // mint_amount = ceiling - supply + 1 pushes supply + mint > ceiling
  let mint_amount = ceiling - supply + 1
  expect under_debt_ceiling(supply, mint_amount, ceiling)
}

/// When supply already equals or exceeds ceiling, any positive mint is rejected
test prop_supply_at_ceiling_rejects_any_mint(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 500)),
) fail {
  let (ceiling, mint_amount) = vals
  // supply == ceiling, so current_supply + mint_amount > debt_ceiling for any mint_amount > 0
  expect under_debt_ceiling(ceiling, mint_amount, ceiling)
}