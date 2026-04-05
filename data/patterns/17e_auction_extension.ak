use aiken/fuzz

/// Anti-sniping: a bid placed near the end extends the deadline by `extension`
fn extended_deadline(
  bid_slot:      Int,
  current_end:   Int,
  extension:     Int,
  snipe_window:  Int,
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
  end:      Int,
  ext:      Int,
  win:      Int,
) -> Bool {
  extended_deadline(bid_slot, end, ext, win) >= end
}

/// Bid far from end does not extend
fn early_bid_no_extension(bid_slot: Int, end: Int, ext: Int, win: Int) -> Bool {
  bid_slot + win < end && extended_deadline(bid_slot, end, ext, win) == end
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
    True  -> extended_deadline(bid_slot, end, 10, 0) == end + 10
    False -> extended_deadline(bid_slot, end, 10, 0) == end
  }
}
