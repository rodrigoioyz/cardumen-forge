use aiken/fuzz

/// Dutch auction: price decreases linearly from start_price to floor_price
/// over the interval [start_slot, end_slot]
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
