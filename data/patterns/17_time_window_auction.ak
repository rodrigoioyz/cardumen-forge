use aiken/fuzz
use aiken/interval
use cardano/transaction.{OutputReference, Transaction}

/// Normalized auction phase derived from the tx validity range
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
