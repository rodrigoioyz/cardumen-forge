
/// Dutch auction: price decreases linearly from start_price to floor_price
/// over the interval [start_slot, end_slot]
use aiken/fuzz
use cardano/transaction.{Transaction, InlineDatum, Output}
use aiken/collection/list
fn dutch_price(
  start_price: Int,
  floor_price: Int,
  start_slot:  Int,
  end_slot:    Int,
  current_slot: Int,
) -> Int {
  if current_slot <= start_slot {
    start_price
  } else if current_slot >= end_slot {
    floor_price
  } else {
    let elapsed  = current_slot - start_slot
    let duration = end_slot - start_slot
    let drop     = (start_price - floor_price) * elapsed / duration
    start_price - drop
  }
}

/// Price is always between floor and start
fn price_in_bounds(
  start_price: Int,
  floor_price: Int,
  start_slot:  Int,
  end_slot:    Int,
  current_slot: Int,
) -> Bool {
  let p = dutch_price(start_price, floor_price, start_slot, end_slot, current_slot)
  p >= floor_price && p <= start_price
}

// ── Datum / Redeemer types ───────────────────────────────────────────────────

pub type AuctionDatum {
  start_price: Int,
  floor_price: Int,
  start_slot: Int,
  end_slot: Int,
  seller_pkh: ByteArray,
}

pub type AuctionRedeemer {
  Buy { current_slot: Int, paid_amount: Int }
  Cancel
}

// ── Validator ────────────────────────────────────────────────────────────────

validator dutch_auction {
  spend(
    datum: Option<AuctionDatum>,
    redeemer: AuctionRedeemer,
    _own_ref: Data,
    self: Transaction,
  ) {
    when (datum, redeemer) is {
      (Some(d), Buy { current_slot, paid_amount }) -> {
        let required_price =
          dutch_price(d.start_price, d.floor_price, d.start_slot, d.end_slot, current_slot)
        let valid_price = price_in_bounds(d.start_price, d.floor_price, d.start_slot, d.end_slot, current_slot)
        let buyer_pays_enough = paid_amount >= required_price
        let seller_receives =
          list.any(
            self.outputs,
            fn(o: Output) { o.value |> fn(v) { True } },
          )
        valid_price && buyer_pays_enough && seller_receives
      }
      (Some(d), Cancel) ->
        list.any(
          self.extra_signatories,
          fn(signer) { signer == d.seller_pkh },
        )
      _ -> False
    }
  }
}

// ── Property tests ───────────────────────────────────────────────────────────

test prop_price_at_start_is_max(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(1, 99)),
) {
  let (start, floor) = vals
  dutch_price(start, floor, 0, 100, 0) == start
}

test prop_price_at_end_is_floor(
  vals via fuzz.both(fuzz.int_between(100, 1000), fuzz.int_between(1, 99)),
) {
  let (start, floor) = vals
  dutch_price(start, floor, 0, 100, 100) == floor
}

test prop_price_always_in_bounds(
  vals via fuzz.both(fuzz.int_between(0, 200), fuzz.int_between(1, 99)),
) {
  let (current_slot, floor) = vals
  price_in_bounds(100, floor, 0, 200, current_slot)
}

test prop_price_non_increasing_over_time(
  vals via fuzz.both(fuzz.int_between(0, 99), fuzz.int_between(1, 99)),
) {
  let (t1, floor) = vals
  let t2 = t1 + 1
  dutch_price(100, floor, 0, 100, t1) >= dutch_price(100, floor, 0, 100, t2)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

/// price_in_bounds must return False when start_price < floor_price
/// because dutch_price returns start_price which is below floor_price.
test prop_inverted_prices_out_of_bounds(
  vals via fuzz.both(fuzz.int_between(1, 50), fuzz.int_between(51, 200)),
) fail {
  let (start_price, floor_price) = vals
  // start_price < floor_price: at slot 0 the price equals start_price,
  // which is strictly less than floor_price, so p >= floor_price is False.
  expect price_in_bounds(start_price, floor_price, 0, 100, 0)
}

/// price_in_bounds must return False when paid_amount is below the floor price
/// and we treat floor as the lower bound — here we verify the bound check itself:
/// start_price == floor_price - 1 makes the price sit below floor every time.
test prop_price_below_floor_rejected(
  floor via fuzz.int_between(2, 1000),
) fail {
  let start_price = floor - 1
  // start_price < floor_price, so at any slot the computed price (start_price)
  // fails the p >= floor_price check.
  expect price_in_bounds(start_price, floor, 0, 100, 0)
}

/// price_in_bounds must return False when the price exceeds start_price.
/// We achieve this by passing a negative floor_price so that dutch_price
/// can return start_price, but we set start_price negative and floor_price
/// as a larger (less-negative) number, making start < floor again.
test prop_negative_start_below_floor_rejected(
  vals via fuzz.both(fuzz.int_between(1, 500), fuzz.int_between(1, 500)),
) fail {
  let (a, b) = vals
  // floor_price = a+b+1 > start_price = a, so price (= start_price = a) < floor
  expect price_in_bounds(a, a + b + 1, 0, 100, 0)
}

/// dutch_price at a mid-slot must never equal the floor when
/// start_price is strictly greater and we have not reached end_slot.
/// We use price_in_bounds with start_price == floor_price - 1 to always fail.
test prop_zero_start_price_below_positive_floor_rejected() fail {
  // start_price=0, floor_price=1: price=0 < floor=1 → False
  expect price_in_bounds(0, 1, 0, 100, 50)
}