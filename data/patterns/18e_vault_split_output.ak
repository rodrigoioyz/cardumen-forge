use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName}
use cardano/fuzz as cfuzz

/// On withdrawal, the extracted qty plus remaining qty must equal original total
fn split_valid(
  withdrawn_qty: Int,
  remaining_qty: Int,
  original_qty:  Int,
) -> Bool {
  withdrawn_qty > 0 && remaining_qty >= 0 && withdrawn_qty + remaining_qty == original_qty
}

/// Token in mint dict has negative qty for withdrawal
fn withdrawal_qty(tokens: dict.Dict<AssetName, Int>) -> Option<Int> {
  when dict.to_pairs(tokens) is {
    [Pair(_, qty)] -> if qty < 0 { Some(-qty) } else { None }
    _              -> None
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_split_sums_to_original(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(0, 500)),
) {
  let (withdrawn, remaining) = vals
  split_valid(withdrawn, remaining, withdrawn + remaining)
}

test prop_zero_withdrawal_rejected(
  remaining via fuzz.int_between(0, 1000),
) {
  !split_valid(0, remaining, remaining)
}

test prop_over_withdrawal_rejected(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(1, 500)),
) {
  let (withdrawn, original) = vals
  // withdrawn > original means remaining would be negative
  !split_valid(withdrawn + original + 1, 0, original)
}

test prop_withdrawal_qty_from_dict(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_between(1, 1000)),
) {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, -qty)
  withdrawal_qty(tokens) == Some(qty)
}
