use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName}

/// Minimum deposit required before any LP tokens are issued
fn meets_min_deposit(input_a: Int, input_b: Int, min_deposit: Int) -> Bool {
  input_a >= min_deposit && input_b >= min_deposit
}

/// LP issued only if deposit exceeds minimum and reserves are positive
fn safe_lp_for_deposit(
  input_a:    Int,
  input_b:    Int,
  reserve_a:  Int,
  reserve_b:  Int,
  total_lp:   Int,
  min_deposit: Int,
) -> Option<Int> {
  if !meets_min_deposit(input_a, input_b, min_deposit) {
    None
  } else if reserve_a <= 0 || reserve_b <= 0 {
    None
  } else {
    let lp_a = input_a * total_lp / reserve_a
    let lp_b = input_b * total_lp / reserve_b
    Some(if lp_a <= lp_b { lp_a } else { lp_b })
  }
}

fn mint_amount_valid(
  tokens:   dict.Dict<AssetName, Int>,
  expected: Int,
) -> Bool {
  when dict.to_pairs(tokens) is {
    [Pair(_, qty)] -> qty == expected
    _              -> False
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_below_min_deposit_returns_none(
  vals via fuzz.both(fuzz.int_between(1, 99), fuzz.int_at_least(100)),
) {
  let (small, min_dep) = vals
  safe_lp_for_deposit(small, small, 100, 100, 1000, min_dep) == None
}

test prop_above_min_deposit_returns_some(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(1, 99)),
) {
  let (input, min_dep) = vals
  safe_lp_for_deposit(input, input, 100, 100, 1000, min_dep) != None
}

test prop_equal_deposits_equal_lp(
  vals via fuzz.both(fuzz.int_between(10, 500), fuzz.int_at_least(1)),
) {
  let (input, reserve) = vals
  when safe_lp_for_deposit(input, input, reserve, reserve, 1000, 1) is {
    Some(lp) -> lp == input * 1000 / reserve
    None     -> False
  }
}

test prop_mint_amount_valid_exact() {
  let tokens = dict.empty |> dict.insert(#"aa", 42)
  mint_amount_valid(tokens, 42)
}
