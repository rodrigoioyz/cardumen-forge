use aiken/collection/list
use aiken/fuzz
use cardano/assets.{lovelace_of}
use cardano/transaction.{Output, OutputReference, Transaction}

pub type CdpDatum {
  owner:        ByteArray,
  collateral:   Int,
  debt:         Int,
  asset_tier:   Int,
}

pub type CdpRedeemer {
  Repay
  Liquidate
}

/// Return the liquidation ratio for the asset tier (1=stable, 2=volatile, 3=exotic)
fn tier_ratio(tier: Int) -> Int {
  if tier == 1 {
    110
  } else if tier == 2 {
    130
  } else {
    150
  }
}

fn is_undercollateralized(collateral: Int, debt: Int, ratio: Int) -> Bool {
  debt > 0 && collateral * 100 < debt * ratio
}

fn liquidator_pays_debt(
  outputs:       List<Output>,
  owner_addr:    Output,
  debt_lovelace: Int,
) -> Bool {
  let paid =
    list.foldl(
      outputs,
      0,
      fn(o, acc) {
        if o.address == owner_addr.address {
          acc + lovelace_of(o.value)
        } else {
          acc
        }
      },
    )
  paid >= debt_lovelace
}

validator cdp_tiered_ratio {
  spend(
    datum: Option<CdpDatum>,
    redeemer: CdpRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let ratio = tier_ratio(d.asset_tier)
    when redeemer is {
      Repay -> list.has(self.extra_signatories, d.owner)
      Liquidate -> is_undercollateralized(d.collateral, d.debt, ratio)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_tier1_ratio() {
  tier_ratio(1) == 110
}

test prop_tier2_ratio() {
  tier_ratio(2) == 130
}

test prop_tier3_ratio() {
  tier_ratio(3) == 150
}

test prop_tiered_undercollateralized(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_between(1, 3)),
) {
  let (debt, tier) = vals
  let ratio = tier_ratio(tier)
  // just below the ratio threshold
  is_undercollateralized(debt * (ratio - 1), debt * 100, ratio)
}
