use aiken/fuzz

/// LP minting is capped at a protocol-defined maximum total supply
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
