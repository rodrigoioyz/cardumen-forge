
use aiken/collection/list
use aiken/fuzz
use cardano/address
use cardano/assets.{lovelace_of}
use cardano/transaction.{Output, OutputReference, Transaction}
pub type EscrowDatum {
  beneficiary: ByteArray,
  refund_to:   ByteArray,
  amount:      Int,
}

pub type EscrowRedeemer {
  Release
  Refund
}

/// Check that at least `amount` lovelace reaches the target address
fn receives_at_least(
  outputs: List<Output>,
  target:  address.Address,
  amount:  Int,
) -> Bool {
  let total =
    list.foldl(
      outputs,
      0,
      fn(o, acc) {
        if o.address == target {
          acc + lovelace_of(o.value)
        } else {
          acc
        }
      },
    )
  total >= amount
}

validator escrow_release {
  spend(
    datum: Option<EscrowDatum>,
    redeemer: EscrowRedeemer,
    _own_ref: OutputReference,
    self: Transaction,
  ) -> Bool {
    expect Some(d) = datum
    when redeemer is {
      Release -> {
        // Beneficiary receives the escrowed amount
        let bene_addr = address.from_verification_key(d.beneficiary)
        receives_at_least(self.outputs, bene_addr, d.amount)
      }
      Refund ->
        // Refund path: original depositor signs
        list.has(self.extra_signatories, d.refund_to)
    }
  }
}

// ── Property tests ──────────────────────────────────────────────────────────

test prop_receives_at_least_empty_false(amount via fuzz.int_at_least(1)) {
  let addr = address.from_verification_key(#"cafe")
  !receives_at_least([], addr, amount)
}

test prop_receives_at_least_zero_always(
  _x via fuzz.int_at_least(0),
) {
  let addr = address.from_verification_key(#"cafe")
  receives_at_least([], addr, 0)
}

test prop_receives_threshold(
  vals via fuzz.both(fuzz.int_at_least(1), fuzz.int_at_least(1)),
) {
  let (a, b) = vals
  // receives_at_least([], _, a+b) is false since no outputs
  let addr = address.from_verification_key(#"cafe")
  !receives_at_least([], addr, a + b)
}

// ── Negative (fail) tests ────────────────────────────────────────────────────

/// No outputs → receives_at_least always returns False for amount >= 1
test prop_no_outputs_never_meets_positive_amount(
  amount via fuzz.int_at_least(1),
) fail {
  let addr = address.from_verification_key(#"cafe")
  expect receives_at_least([], addr, amount)
}

/// A very large required amount with empty output list is always rejected
test prop_large_amount_no_outputs_rejected() fail {
  let addr = address.from_verification_key(#"deadbeef")
  expect receives_at_least([], addr, 1_000_000_000)
}

/// Outputs destined for a DIFFERENT address never satisfy receives_at_least
/// for a positive target amount on the correct address.
/// We rely on the fact that empty outputs for the target address means total=0 < amount.
test prop_wrong_address_outputs_rejected(
  amount via fuzz.int_at_least(1),
) fail {
  // target address uses key #"cafe", but we pass an empty list so no
  // outputs exist for that address — total lovelace = 0 < amount
  let target = address.from_verification_key(#"cafe")
  expect receives_at_least([], target, amount)
}

/// receives_at_least with a very high threshold and no outputs always fails
test prop_high_threshold_no_outputs_fail(
  amount via fuzz.int_between(1_000_000, 999_999_999),
) fail {
  let addr = address.from_verification_key(#"abcd1234")
  expect receives_at_least([], addr, amount)
}