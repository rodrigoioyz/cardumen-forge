use aiken/collection/dict
use aiken/fuzz
use aiken/interval
use cardano/assets.{AssetName}
use cardano/fuzz as cfuzz

/// Cooldown: withdrawals allowed only after `last_withdrawal + cooldown_slots`
fn cooldown_elapsed(
  validity_range:  interval.Interval,
  last_withdrawal: Int,
  cooldown_slots:  Int,
) -> Bool {
  interval.is_entirely_after(validity_range, last_withdrawal + cooldown_slots)
}

/// Deposit has no cooldown restriction
fn deposit_valid(tokens: dict.Dict<AssetName, Int>) -> Bool {
  when dict.to_pairs(tokens) is {
    [Pair(_, qty)] -> qty > 0
    _              -> False
  }
}

/// Withdrawal requires cooldown and a single negative token
fn withdrawal_valid(
  tokens:          dict.Dict<AssetName, Int>,
  validity_range:  interval.Interval,
  last_withdrawal: Int,
  cooldown_slots:  Int,
) -> Bool {
  cooldown_elapsed(validity_range, last_withdrawal, cooldown_slots)
    && (
      when dict.to_pairs(tokens) is {
        [Pair(_, qty)] -> qty < 0
        _              -> False
      }
    )
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
