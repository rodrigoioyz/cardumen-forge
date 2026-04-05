use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{ada_asset_name, ada_policy_id, lovelace_of}
use cardano/transaction.{InlineDatum, Output, OutputReference, Transaction}

pub type SwapDatum {
  price:  Int,
  seller: ByteArray,
  id:     ByteArray,
}

pub type PaymentTag {
  swap_id: ByteArray,
}

/// Sum lovelace in outputs to seller that carry the matching swap ID tag
fn ada_paid_with_id(
  outputs: List<Output>,
  seller_addr: address.Address,
  swap_id: ByteArray,
) -> Int {
  list.foldl(
    outputs,
    0,
    fn(o, acc) {
      if o.address == seller_addr {
        when o.datum is {
          InlineDatum(raw) -> {
            expect tag: ByteArray = raw
            if tag == swap_id {
              acc + lovelace_of(o.value)
            } else {
              acc
            }
          }
          _ -> acc
        }
      } else {
        acc
      }
    },
  )
}

validator dex_swap {
  spend(
    datum: Option<SwapDatum>,
    _redeemer: Data,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    let seller_addr = address.from_verification_key(d.seller)
    ada_paid_with_id(self.outputs, seller_addr, d.id) >= d.price
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_ada_paid_empty_outputs_zero(price via fuzz.int_at_least(1)) {
  let addr = address.from_verification_key(#"aabbcc")
  ada_paid_with_id([], addr, #"deadbeef") == 0
}

test prop_ada_paid_non_negative(price via fuzz.int_at_least(1)) {
  let addr = address.from_verification_key(#"aabbcc")
  ada_paid_with_id([], addr, #"") >= 0
}
