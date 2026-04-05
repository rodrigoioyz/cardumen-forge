#!/usr/bin/env python3
"""Adds 15 withdraw prompts to benchmark_v2.json."""
import json
from pathlib import Path

BM = Path(__file__).parent.parent / "eval" / "benchmark_v2.json"
data = json.load(open(BM))

withdraw_prompts = [
  {
    "id": "withdraw_01", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `staking_owner` that allows rewards withdrawal only if the owner (ByteArray validator parameter) has signed the transaction. Use self.extra_signatories and list.has.",
    "reference_solution": "use aiken/collection/list\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\nvalidator staking_owner(owner: ByteArray) {\n  withdraw(_redeemer: Data, _account: Credential, self: Transaction) {\n    list.has(self.extra_signatories, owner)\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "extra_signatories", "list.has"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime", "self.time"]
  },
  {
    "id": "withdraw_02", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `min_rewards` that allows withdrawal only if the amount is at least min_amount (Int validator parameter). Read the amount from self.withdrawals using the account credential and dict.get.",
    "reference_solution": "use aiken/collection/dict\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\nvalidator min_rewards(min_amount: Int) {\n  withdraw(_redeemer: Data, account: Credential, self: Transaction) {\n    when dict.get(self.withdrawals, account) is {\n      None -> False\n      Some(amount) -> amount >= min_amount\n    }\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "self.withdrawals", "min_amount", "dict.get"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_03", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `timed_staking` that allows withdrawal only after a deadline (Int validator parameter). Use interval.is_entirely_after on self.validity_range.",
    "reference_solution": "use aiken/interval\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\nvalidator timed_staking(deadline: Int) {\n  withdraw(_redeemer: Data, _account: Credential, self: Transaction) {\n    interval.is_entirely_after(self.validity_range, deadline)\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "validity_range", "deadline", "interval"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime", "self.time"]
  },
  {
    "id": "withdraw_04", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `multisig_staking` where the redeemer carries required_signers: List<ByteArray> and threshold: Int. Allow withdrawal only if at least threshold signers are present in extra_signatories.",
    "reference_solution": "use aiken/collection/list\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\npub type StakeRedeemer {\n  required_signers: List<ByteArray>,\n  threshold: Int,\n}\n\nvalidator multisig_staking {\n  withdraw(redeemer: StakeRedeemer, _account: Credential, self: Transaction) {\n    let present = list.count(\n      self.extra_signatories,\n      fn(sig) { list.has(redeemer.required_signers, sig) },\n    )\n    present >= redeemer.threshold\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "extra_signatories", "list.count", "threshold"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_05", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `nft_gated_staking` that allows withdrawal only if an input holds a specific NFT. policy_id and asset_name are ByteArray validator parameters. Use assets.quantity_of on input values.",
    "reference_solution": "use aiken/collection/list\nuse cardano/address.{Credential}\nuse cardano/assets\nuse cardano/transaction.{Transaction}\n\nvalidator nft_gated_staking(policy_id: ByteArray, asset_name: ByteArray) {\n  withdraw(_redeemer: Data, _account: Credential, self: Transaction) {\n    list.any(\n      self.inputs,\n      fn(input) {\n        assets.quantity_of(input.output.value, policy_id, asset_name) > 0\n      },\n    )\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "self.inputs", "assets.quantity_of", "policy_id"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_06", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `two_key_staking` that requires both a hot_key and cold_key (ByteArray validator parameters) to sign for any withdrawal. Both must appear in extra_signatories.",
    "reference_solution": "use aiken/collection/list\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\nvalidator two_key_staking(hot_key: ByteArray, cold_key: ByteArray) {\n  withdraw(_redeemer: Data, _account: Credential, self: Transaction) {\n    list.has(self.extra_signatories, hot_key)\n      && list.has(self.extra_signatories, cold_key)\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "extra_signatories", "hot_key", "cold_key"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_07", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `fee_split_staking` that allows withdrawal only if an output pays at least fee_amount (Int validator parameter) lovelace to a fee_collector address (ByteArray parameter). Use assets.lovelace_of.",
    "reference_solution": "use aiken/collection/list\nuse cardano/address.{Credential, VerificationKey}\nuse cardano/assets\nuse cardano/transaction.{Transaction}\n\nvalidator fee_split_staking(fee_collector: ByteArray, fee_amount: Int) {\n  withdraw(_redeemer: Data, _account: Credential, self: Transaction) {\n    list.any(\n      self.outputs,\n      fn(output) {\n        output.address.payment_credential == VerificationKey(fee_collector)\n          && assets.lovelace_of(output.value) >= fee_amount\n      },\n    )\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "self.outputs", "fee_amount", "assets.lovelace_of"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_08", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `paused_staking` with parameters owner: ByteArray and paused: Bool. Reject all withdrawals when paused is True. When False, allow only if owner signed.",
    "reference_solution": "use aiken/collection/list\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\nvalidator paused_staking(owner: ByteArray, paused: Bool) {\n  withdraw(_redeemer: Data, _account: Credential, self: Transaction) {\n    !paused && list.has(self.extra_signatories, owner)\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "paused", "extra_signatories"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_09", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `rewards_accumulator` that allows withdrawal only if the amount in self.withdrawals for the staking account is at least 1,000,000 lovelace. Use dict.get to read the withdrawal amount.",
    "reference_solution": "use aiken/collection/dict\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\nvalidator rewards_accumulator {\n  withdraw(_redeemer: Data, account: Credential, self: Transaction) {\n    when dict.get(self.withdrawals, account) is {\n      None -> False\n      Some(amount) -> amount >= 1000000\n    }\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "self.withdrawals", "account", "dict.get"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_10", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `vesting_staking` with parameters beneficiary: ByteArray and vesting_end: Int. Allow withdrawal only after vesting_end (use interval.is_entirely_after) and if beneficiary signed.",
    "reference_solution": "use aiken/collection/list\nuse aiken/interval\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\nvalidator vesting_staking(beneficiary: ByteArray, vesting_end: Int) {\n  withdraw(_redeemer: Data, _account: Credential, self: Transaction) {\n    let after_vesting = interval.is_entirely_after(self.validity_range, vesting_end)\n    let signed = list.has(self.extra_signatories, beneficiary)\n    after_vesting && signed\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "validity_range", "vesting_end", "extra_signatories", "interval"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_11", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `conditional_staking` where the redeemer is a Bool (emergency flag). If True (emergency), require both owner and guardian (validator parameters) to sign. If False, only owner needs to sign.",
    "reference_solution": "use aiken/collection/list\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\nvalidator conditional_staking(owner: ByteArray, guardian: ByteArray) {\n  withdraw(emergency: Bool, _account: Credential, self: Transaction) {\n    if emergency {\n      list.has(self.extra_signatories, owner)\n        && list.has(self.extra_signatories, guardian)\n    } else {\n      list.has(self.extra_signatories, owner)\n    }\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "extra_signatories", "owner", "guardian"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_12", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `governance_withdraw` with a council: List<ByteArray> validator parameter. Allow withdrawal only if at least 2 council members have signed the transaction.",
    "reference_solution": "use aiken/collection/list\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\nvalidator governance_withdraw(council: List<ByteArray>) {\n  withdraw(_redeemer: Data, _account: Credential, self: Transaction) {\n    let approvals = list.count(\n      self.extra_signatories,\n      fn(sig) { list.has(council, sig) },\n    )\n    approvals >= 2\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "extra_signatories", "list.count", "council"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_13", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `override_staking` with parameters owner: ByteArray, override_key: ByteArray, and deadline: Int. Before deadline, only owner can withdraw. After deadline, only override_key can withdraw.",
    "reference_solution": "use aiken/collection/list\nuse aiken/interval\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\nvalidator override_staking(owner: ByteArray, override_key: ByteArray, deadline: Int) {\n  withdraw(_redeemer: Data, _account: Credential, self: Transaction) {\n    let after_deadline = interval.is_entirely_after(self.validity_range, deadline)\n    if after_deadline {\n      list.has(self.extra_signatories, override_key)\n    } else {\n      list.has(self.extra_signatories, owner)\n    }\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "extra_signatories", "override_key", "deadline", "interval"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_14", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `tiered_staking` with parameters owner: ByteArray, guardian: ByteArray, and min_amount: Int. For small withdrawals (< min_amount), only owner needs to sign. For large withdrawals, both owner and guardian must sign.",
    "reference_solution": "use aiken/collection/dict\nuse aiken/collection/list\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\nvalidator tiered_staking(owner: ByteArray, guardian: ByteArray, min_amount: Int) {\n  withdraw(_redeemer: Data, account: Credential, self: Transaction) {\n    let amount = when dict.get(self.withdrawals, account) is {\n      None -> 0\n      Some(a) -> a\n    }\n    if amount >= min_amount {\n      list.has(self.extra_signatories, owner)\n        && list.has(self.extra_signatories, guardian)\n    } else {\n      list.has(self.extra_signatories, owner)\n    }\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "self.withdrawals", "extra_signatories", "min_amount"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
  {
    "id": "withdraw_15", "category": "withdraw",
    "prompt": "Write an Aiken v3 withdraw validator called `dao_staking` with a council: List<ByteArray> validator parameter. The redeemer carries approved: Bool. Allow withdrawal only if approved is True and at least 2 council members signed.",
    "reference_solution": "use aiken/collection/list\nuse cardano/address.{Credential}\nuse cardano/transaction.{Transaction}\n\npub type DaoRedeemer {\n  approved: Bool,\n}\n\nvalidator dao_staking(council: List<ByteArray>) {\n  withdraw(redeemer: DaoRedeemer, _account: Credential, self: Transaction) {\n    let approvals = list.count(\n      self.extra_signatories,\n      fn(sig) { list.has(council, sig) },\n    )\n    redeemer.approved && approvals >= 2\n  }\n}\n",
    "must_contain": ["withdraw(", "Credential", "extra_signatories", "list.count", "approved", "council"],
    "must_not_contain": ["fn withdraw", "import ", "PosixTime"]
  },
]

data.extend(withdraw_prompts)
with open(BM, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print(f"Done. Total prompts: {len(data)}")
