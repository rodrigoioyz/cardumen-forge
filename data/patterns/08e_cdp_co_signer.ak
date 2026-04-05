
use aiken/collection/list
use aiken/fuzz
use cardano/assets.{lovelace_of}
use cardano/fuzz as cfuzz
use cardano/transaction.{Output, OutputReference, Transaction}
pub type CdpDatum {
  owner:             ByteArray,
  co_signers:        List<ByteArray>,
  collateral:        Int,
  debt:              Int,
  liquidation_ratio: Int,
}

pub type CdpRedeemer {
  Repay
  Liquidate
}

fn is_undercollateralized(collateral: Int, debt: Int, ratio: Int) -> Bool {
  debt > 0 && collateral * 100 < debt * ratio
}

/// Owner OR any co-signer may repay
fn authorised_repay(
  signatories: List<ByteArray>,
  owner:       ByteArray,
  co_signers:  List<ByteArray>,
) -> Bool {
  list.has(signatories, owner) || list.any(
    co_signers,
    fn(cs) { list.has(signatories, cs) },
  )
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

validator cdp_co_signer {
  spend(
    datum: Option<CdpDatum>,
    redeemer: CdpRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      Repay ->
        authorised_repay(self.extra_signatories, d.owner, d.co_signers)
      Liquidate ->
        is_undercollateralized(d.collateral, d.debt, d.liquidation_ratio)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_co_signer_owner_authorised(
  keys via fuzz.list_between(cfuzz.verification_key_hash(), 1, 5),
) {
  let owner = #"aabb"
  authorised_repay([owner], owner, keys)
}

test prop_co_signer_cosigner_authorised(
  co via cfuzz.verification_key_hash(),
) {
  authorised_repay([co], #"deadbeef", [co])
}

test prop_co_signer_no_match_fails(
  keys via fuzz.list_between(cfuzz.verification_key_hash(), 0, 5),
) {
  !authorised_repay([], #"deadbeef", keys)
}

test prop_undercollateralized_at_boundary(debt via fuzz.int_at_least(1)) {
  is_undercollateralized(debt * 119, debt * 100, 120)
}

// ── Negative / fail tests ────────────────────────────────────────────────────

// No signatories means neither owner nor any co-signer can be found
test prop_empty_signatories_unauthorised(
  owner via cfuzz.verification_key_hash(),
) fail {
  expect authorised_repay([], owner, [owner])
}

// A well-collateralised position (collateral * 100 >= debt * ratio) must NOT
// be flagged as undercollateralised.  Here collateral = debt * ratio, so
// collateral * 100 == debt * ratio * 100, which is NOT strictly less than
// debt * ratio * 100 — the helper must return False.
test prop_healthy_position_not_undercollateralized(
  vals via fuzz.both(fuzz.int_between(1, 200), fuzz.int_between(1, 300)),
) fail {
  let (ratio, debt) = vals
  // collateral is large enough that collateral * 100 >= debt * ratio
  let collateral = debt * ratio
  expect is_undercollateralized(collateral, debt, ratio)
}

// Zero debt means a position can never be undercollateralised regardless of
// collateral or ratio — the guard `debt > 0` makes the helper return False.
test prop_zero_debt_not_undercollateralized(
  collateral via fuzz.int_between(0, 1_000_000),
) fail {
  expect is_undercollateralized(collateral, 0, 150)
}

// A co-signer list that is entirely disjoint from the signatory set must
// not grant authorisation when the owner is also absent.
test prop_disjoint_cosigners_unauthorised() fail {
  // signatories = [#"1111"], owner = #"2222", co_signers = [#"3333"]
  expect authorised_repay([#"1111"], #"2222", [#"3333"])
}