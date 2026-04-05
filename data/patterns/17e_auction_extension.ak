
/// Anti-sniping: a bid placed near the end extends the deadline by `extension`
use aiken/fuzz
use cardano/transaction.{Transaction, InlineDatum}
use cardano/assets.{PolicyId}
fn extended_deadline(
  bid_slot: Int,
  current_end: Int,
  extension: Int,
  snipe_window: Int,
) -> Int {
  if bid_slot + snipe_window >= current_end {
    current_end + extension
  } else {
    current_end
  }
}

/// Deadline is never shortened by extension
fn extension_non_decreasing(
  bid_slot: Int,
  end: Int,
  ext: Int,
  win: Int,
) -> Bool {
  extended_deadline(bid_slot, end, ext, win) >= end
}

/// Bid far from end does not extend
fn early_bid_no_extension(bid_slot: Int, end: Int, ext: Int, win: Int) -> Bool {
  bid_slot + win < end && extended_deadline(bid_slot, end, ext, win) == end
}

// ── Datum / Redeemer ─────────────────────────────────────────────────────────

pub type AuctionDatum {
  current_end: Int,
  extension: Int,
  snipe_window: Int,
  prev_bid: Int,
  min_increment: Int,
}

pub type BidRedeemer {
  bid_slot: Int,
  bid_amount: Int,
}

// ── Validator ────────────────────────────────────────────────────────────────

validator auction_extension(_policy_id: PolicyId) {
  spend(
    datum: Option<AuctionDatum>,
    redeemer: BidRedeemer,
    _output_ref,
    self: Transaction,
  ) {
    expect Some(d) = datum
    let BidRedeemer { bid_slot, bid_amount } = redeemer
    let new_end = extended_deadline(bid_slot, d.current_end, d.extension, d.snipe_window)
    let deadline_ok = extension_non_decreasing(bid_slot, d.current_end, d.extension, d.snipe_window)
    let no_early_sneak = !early_bid_no_extension(bid_slot, d.current_end, d.extension, d.snipe_window) || new_end == d.current_end
    let bid_sufficient = bid_amount >= d.prev_bid + d.min_increment
    let _ = self.inputs
    deadline_ok && no_early_sneak && bid_sufficient
  }

  else(_) {
    fail
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_snipe_extends_deadline(
  vals via fuzz.both(fuzz.int_between(1, 100), fuzz.int_between(1, 50)),
) {
  let (end, ext) = vals
  // bid at exact end triggers extension
  extended_deadline(end, end, ext, 0) == end + ext
}

test prop_early_bid_unchanged(
  vals via fuzz.both(fuzz.int_between(200, 500), fuzz.int_between(1, 50)),
) {
  let (end, ext) = vals
  early_bid_no_extension(0, end, ext, 10)
}

test prop_deadline_never_decreases(
  vals via fuzz.both(fuzz.int_between(1, 1000), fuzz.int_between(1, 100)),
) {
  let (bid_slot, end) = vals
  extension_non_decreasing(bid_slot, end, 50, 10)
}

test prop_no_extension_when_window_zero(
  bid_slot via fuzz.int_between(0, 1000),
) {
  // snipe_window == 0 means any bid at or after end triggers extension
  let end = 500
  when bid_slot >= end is {
    True -> extended_deadline(bid_slot, end, 10, 0) == end + 10
    False -> extended_deadline(bid_slot, end, 10, 0) == end
  }
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// early_bid_no_extension returns False when bid_slot + win >= end,
// because the condition bid_slot + win < end is not satisfied.
// Here bid_slot >= end and win >= 0 guarantees bid_slot + win >= end.
test prop_late_bid_fails_early_bid_check(
  vals via fuzz.both(fuzz.int_between(500, 1000), fuzz.int_between(0, 50)),
) fail {
  let (bid_slot, win) = vals
  // end = 499, so bid_slot >= 500 > 499, meaning bid_slot + win >= end always
  expect early_bid_no_extension(bid_slot, 499, 10, win)
}

// early_bid_no_extension returns False when ext > 0 and the bid is
// within the snipe window, because extended_deadline != end.
// bid_slot=490, end=500, win=20: 490+20=510 >= 500 so it extends → result != end
test prop_snipe_bid_fails_early_bid_check() fail {
  // bid_slot + win = 490 + 20 = 510 >= 500, so early_bid_no_extension is False
  expect early_bid_no_extension(490, 500, 10, 20)
}

// extension_non_decreasing returns False only if extended_deadline < end,
// which cannot happen by construction — so we target early_bid_no_extension
// with a bid exactly at the boundary where extension fires but ext is negative.
// With a negative extension the new_end < end, making extension_non_decreasing False.
test prop_negative_extension_violates_non_decreasing(
  ext via fuzz.int_between(-500, -1),
) fail {
  // bid at end with negative extension: extended_deadline = end + ext < end
  expect extension_non_decreasing(100, 100, ext, 0)
}

// early_bid_no_extension is False when bid_slot + win >= end regardless of ext,
// because the first conjunct (bid_slot + win < end) fails.
// Use bid_slot = end to guarantee bid_slot + win >= end for any win >= 0.
test prop_bid_at_end_fails_early_bid_check(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(0, 100)),
) fail {
  let (end, win) = vals
  // bid_slot == end, so bid_slot + win = end + win >= end — first conjunct False
  expect early_bid_no_extension(end, end, 1, win)
}