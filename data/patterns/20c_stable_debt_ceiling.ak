use aiken/fuzz

/// Global debt ceiling: total minted stablecoin must not exceed the cap
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
