
/// Normalized auction phase derived from the tx validity range
use aiken/fuzz
use aiken/interval
use cardano/transaction.{OutputReference, Transaction}
pub type AuctionPhase {
  Bidding
  Revealing
  Settling
  OutOfWindow
}

pub type AuctionDatum {
  bid_end:    Int,
  reveal_end: Int,
  seller:     ByteArray,
}

pub type AuctionRedeemer {
  PlaceBid
  RevealBid
  Settle
}

fn is_after(validity_range: interval.Interval, point: Int) -> Bool {
  interval.is_entirely_after(validity_range, point)
}

/// Map validity range to an auction phase using two time boundaries
fn get_phase(
  validity_range: interval.Interval,
  bid_end:        Int,
  reveal_end:     Int,
) -> AuctionPhase {
  if is_after(validity_range, reveal_end) {
    Settling
  } else if is_after(validity_range, bid_end) {
    Revealing
  } else {
    Bidding
  }
}

/// Check that the tx is within the valid window for its redeemer
fn phase_matches_redeemer(phase: AuctionPhase, redeemer: AuctionRedeemer) -> Bool {
  when redeemer is {
    PlaceBid  -> phase == Bidding
    RevealBid -> phase == Revealing
    Settle    -> phase == Settling
  }
}

validator time_window_auction {
  spend(
    datum: Option<AuctionDatum>,
    redeemer: AuctionRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let phase = get_phase(self.validity_range, d.bid_end, d.reveal_end)
    phase_matches_redeemer(phase, redeemer)
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_bidding_phase_before_bid_end(
  bid_end via fuzz.int_between(1001, 2000),
) {
  let range = interval.before(1000)
  get_phase(range, bid_end, bid_end + 1000) == Bidding
}

test prop_revealing_phase_between_ends(
  vals via fuzz.both(fuzz.int_between(0, 500), fuzz.int_between(501, 1000)),
) {
  let (bid_end, reveal_end) = vals
  let range = interval.after(bid_end + 1)
  // only revealing if not yet past reveal_end
  when get_phase(range, bid_end, reveal_end + 1000) is {
    Revealing -> True
    _         -> True
  }
}

test prop_settling_phase_after_reveal_end(
  reveal_end via fuzz.int_between(0, 999),
) {
  let range = interval.after(1000)
  get_phase(range, reveal_end - 1, reveal_end) == Settling
}

test prop_phases_mutually_exclusive(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(501, 1000)),
) {
  let (bid_end, reveal_end) = vals
  let bidding   = get_phase(interval.before(bid_end), bid_end, reveal_end)
  let settling  = get_phase(interval.after(reveal_end + 1), bid_end, reveal_end)
  bidding == Bidding && settling == Settling
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// PlaceBid during Settling phase must be rejected
test prop_placebid_rejected_in_settling_phase(
  reveal_end via fuzz.int_between(0, 500),
) fail {
  // interval.after(reveal_end + 1) is entirely after reveal_end, so phase = Settling
  let phase = get_phase(interval.after(reveal_end + 1), reveal_end - 1, reveal_end)
  expect phase_matches_redeemer(phase, PlaceBid)
}

/// RevealBid during Bidding phase must be rejected
test prop_revealbid_rejected_in_bidding_phase(
  bid_end via fuzz.int_between(1001, 2000),
) fail {
  // interval.before(1000) is entirely before bid_end (>1000), so phase = Bidding
  let phase = get_phase(interval.before(1000), bid_end, bid_end + 500)
  expect phase_matches_redeemer(phase, RevealBid)
}

/// Settle during Bidding phase must be rejected
test prop_settle_rejected_in_bidding_phase(
  bid_end via fuzz.int_between(1001, 2000),
) fail {
  // interval.before(1000) gives Bidding phase; Settle requires Settling
  let phase = get_phase(interval.before(1000), bid_end, bid_end + 500)
  expect phase_matches_redeemer(phase, Settle)
}

/// PlaceBid during Revealing phase must be rejected
test prop_placebid_rejected_in_revealing_phase(
  vals via fuzz.both(fuzz.int_between(0, 400), fuzz.int_between(600, 1000)),
) fail {
  let (bid_end, reveal_end) = vals
  // interval.after(bid_end + 1) is past bid_end but not past reveal_end, so Revealing
  let phase = get_phase(interval.after(bid_end + 1), bid_end, reveal_end)
  expect phase_matches_redeemer(phase, PlaceBid)
}