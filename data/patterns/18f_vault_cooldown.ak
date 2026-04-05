
/// Cooldown: withdrawals allowed only after `last_withdrawal + cooldown_slots`
use aiken/collection/dict
use aiken/fuzz
use aiken/interval
use cardano/assets.{AssetName}
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}
fn cooldown_elapsed(
  validity_range: interval.Interval,
  last_withdrawal: Int,
  cooldown_slots: Int,
) -> Bool {
  interval.is_entirely_after(validity_range, last_withdrawal + cooldown_slots)
}

/// Deposit has no cooldown restriction
fn deposit_valid(tokens: dict.Dict<AssetName, Int>) -> Bool {
  when dict.to_pairs(tokens) is {
    [Pair(_, qty)] -> qty > 0
    _ -> False
  }
}

/// Withdrawal requires cooldown and a single negative token
fn withdrawal_valid(
  tokens: dict.Dict<AssetName, Int>,
  validity_range: interval.Interval,
  last_withdrawal: Int,
  cooldown_slots: Int,
) -> Bool {
  cooldown_elapsed(validity_range, last_withdrawal, cooldown_slots)
    && (
      when dict.to_pairs(tokens) is {
        [Pair(_, qty)] -> qty < 0
        _ -> False
      }
    )
}

pub type VaultDatum {
  last_withdrawal: Int,
  cooldown_slots: Int,
}

pub type VaultRedeemer {
  Deposit { tokens: dict.Dict<AssetName, Int> }
  Withdraw { tokens: dict.Dict<AssetName, Int> }
}

validator vault_cooldown {
  spend(
    datum: Option<VaultDatum>,
    redeemer: VaultRedeemer,
    _utxo: Data,
    self: Transaction,
  ) {
    expect Some(d) = datum
    when redeemer is {
      Deposit { tokens } -> deposit_valid(tokens)
      Withdraw { tokens } ->
        withdrawal_valid(
          tokens,
          self.validity_range,
          d.last_withdrawal,
          d.cooldown_slots,
        )
    }
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_cooldown_elapsed_after_wait(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(1, 100)),
) {
  let (last, cooldown) = vals
  cooldown_elapsed(interval.after(last + cooldown + 1), last, cooldown)
}

test prop_cooldown_not_elapsed_too_early(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(1, 100)),
) {
  let (last, cooldown) = vals
  !cooldown_elapsed(interval.before(last + cooldown), last, cooldown)
}

test prop_deposit_valid_positive(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_at_least(1)),
) {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, qty)
  deposit_valid(tokens)
}

test prop_withdrawal_valid_after_cooldown(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 100)),
) {
  let (name, cooldown) = vals
  let tokens = dict.empty |> dict.insert(name, -10)
  withdrawal_valid(tokens, interval.after(cooldown + 1), 0, cooldown)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// deposit_valid rejects an empty token dict (no pairs → False branch)
test prop_deposit_invalid_empty_tokens() fail {
  expect deposit_valid(dict.empty)
}

/// deposit_valid rejects zero quantity tokens
test prop_deposit_invalid_zero_qty(
  name via cfuzz.asset_name(),
) fail {
  let tokens = dict.empty |> dict.insert(name, 0)
  expect deposit_valid(tokens)
}

/// deposit_valid rejects negative quantity tokens
test prop_deposit_invalid_negative_qty(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_between(-500, -1)),
) fail {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, qty)
  expect deposit_valid(tokens)
}

/// withdrawal_valid rejects when cooldown has not elapsed
/// (validity_range ends before last_withdrawal + cooldown_slots)
test prop_withdrawal_invalid_before_cooldown(
  vals via fuzz.both(
    cfuzz.asset_name(),
    fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(1, 100)),
  ),
) fail {
  let (name, (last, cooldown)) = vals
  let tokens = dict.empty |> dict.insert(name, -10)
  // interval.before(last + cooldown) ends strictly before the required point
  expect withdrawal_valid(tokens, interval.before(last + cooldown), last, cooldown)
}