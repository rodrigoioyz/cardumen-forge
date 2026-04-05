
/// Minimum deposit required before any LP tokens are issued
use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName, PolicyId, from_asset, tokens}
use cardano/transaction.{Transaction}
fn meets_min_deposit(input_a: Int, input_b: Int, min_deposit: Int) -> Bool {
  input_a >= min_deposit && input_b >= min_deposit
}

/// LP issued only if deposit exceeds minimum and reserves are positive
fn safe_lp_for_deposit(
  input_a: Int,
  input_b: Int,
  reserve_a: Int,
  reserve_b: Int,
  total_lp: Int,
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
  tokens_dict: dict.Dict<AssetName, Int>,
  expected: Int,
) -> Bool {
  when dict.to_pairs(tokens_dict) is {
    [Pair(_, qty)] -> qty == expected
    _ -> False
  }
}

// ── Redeemer type ─────────────────────────────────────────────────────────────

pub type DepositRedeemer {
  input_a: Int,
  input_b: Int,
  reserve_a: Int,
  reserve_b: Int,
  total_lp: Int,
  min_deposit: Int,
}

// ── Validator ─────────────────────────────────────────────────────────────────

validator lp_min_deposit(policy_id: PolicyId) {
  mint(redeemer: DepositRedeemer, _policy: PolicyId, self: Transaction) {
    let DepositRedeemer {
      input_a,
      input_b,
      reserve_a,
      reserve_b,
      total_lp,
      min_deposit,
    } = redeemer

    when
      safe_lp_for_deposit(
        input_a,
        input_b,
        reserve_a,
        reserve_b,
        total_lp,
        min_deposit,
      )
    is {
      None -> False
      Some(expected_lp) -> {
        let minted_tokens = tokens(self.mint, policy_id)
        mint_amount_valid(minted_tokens, expected_lp)
      }
    }
  }

  else(_) {
    fail
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
    None -> False
  }
}

test prop_mint_amount_valid_exact() {
  let token_dict = dict.empty |> dict.insert(#"aa", 42)
  mint_amount_valid(token_dict, 42)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// meets_min_deposit must reject when both inputs are strictly below min_deposit.
/// For any small in [0,99] and min in [100,500], small < min so both conditions fail.
test prop_both_inputs_below_min_rejected(
  vals via fuzz.both(fuzz.int_between(0, 99), fuzz.int_between(100, 500)),
) fail {
  let (small, min_dep) = vals
  expect meets_min_deposit(small, small, min_dep)
}

/// meets_min_deposit must reject when only input_b is below the minimum.
/// input_a passes (200) but input_b in [0,99] is strictly below min_deposit in [100,500].
test prop_one_input_below_min_rejected(
  vals via fuzz.both(fuzz.int_between(0, 99), fuzz.int_between(100, 500)),
) fail {
  let (small_b, min_dep) = vals
  expect meets_min_deposit(200, small_b, min_dep)
}

/// mint_amount_valid must reject an empty dict (no tokens minted at all).
test prop_empty_dict_mint_invalid(
  expected via fuzz.int_between(1, 1000),
) fail {
  expect mint_amount_valid(dict.empty, expected)
}

/// mint_amount_valid must reject when the single minted quantity does not match expected.
/// qty is in [1,100] and expected is in [101,200], so they can never be equal.
test prop_wrong_mint_quantity_rejected(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(101, 200)),
) fail {
  let (qty, expected) = vals
  let token_dict = dict.empty |> dict.insert(#"aa", qty)
  expect mint_amount_valid(token_dict, expected)
}