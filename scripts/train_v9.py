#!/usr/bin/env python3
"""
cardano-dev v9 — Qwen3.5-4B fine-tune on dataset_v23 (4,655 examples, stdlib v3)
Run in Google Colab (GPU runtime). Single-file, no notebooks.
"""

# ============================================
# 1) INSTALACIÓN
# ============================================
import subprocess, sys

subprocess.run([sys.executable, "-m", "pip", "-q", "install", "unsloth"], check=True)
subprocess.run([
    sys.executable, "-m", "pip", "-q", "install", "--no-deps",
    "xformers", "trl", "peft", "accelerate", "bitsandbytes", "datasets", "transformers"
], check=True)

# ============================================
# 2) IMPORTS
# ============================================
import os
import gc
import glob
import torch
from datasets import load_dataset
from transformers import EarlyStoppingCallback
from trl import SFTTrainer, SFTConfig
from unsloth import FastLanguageModel

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
gc.collect()
torch.cuda.empty_cache()

print(f"GPU    : {torch.cuda.get_device_name(0)}")
print(f"VRAM   : {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
print(f"bf16   : {torch.cuda.is_bf16_supported()}")

# ============================================
# 3) SUBIR / DETECTAR DATASET
# ============================================
files_found = glob.glob("*.jsonl")

if files_found:
    v23_candidates = [x for x in files_found if "dataset_v23" in x]
    dataset_path = v23_candidates[0] if v23_candidates else files_found[0]
    print(f"Dataset encontrado: {dataset_path}")
else:
    from google.colab import files as colab_files
    print("Sube dataset_v23.jsonl (4,655 ejemplos, stdlib v3)")
    uploaded = colab_files.upload()
    dataset_path = list(uploaded.keys())[0]

dataset = load_dataset("json", data_files=dataset_path, split="train")
print(f"{len(dataset)} ejemplos cargados")
assert len(dataset) >= 4655, f"Esperados >= 4655 (v23 activo), encontrados {len(dataset)}"

# ============================================
# 4) CONFIG DEL MODELO
# ============================================
MODEL_NAME     = "unsloth/Qwen3.5-4B"
MAX_SEQ_LENGTH = 2048
LOAD_IN_4BIT   = False

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit=LOAD_IN_4BIT,
    dtype=torch.bfloat16,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=32,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_alpha=64,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=3407,
)

trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total     = sum(p.numel() for p in model.parameters())
print(f"Params entrenables : {trainable:,} ({100 * trainable / total:.2f}%)")
print(f"VRAM usada         : {torch.cuda.memory_allocated() / 1e9:.2f} GB")

# ============================================
# 5) FORMATEO DEL DATASET
# ============================================
SYSTEM_PROMPT = """You are an expert Aiken v3 smart contract engineer for the Cardano blockchain.
You write correct, compilable Aiken v3 validators using only verified APIs.

CRITICAL — handler syntax inside validator blocks (NO fn keyword before handler name):
  validator my_contract {
    spend(datum: Option<T>, redeemer: T, own_ref: OutputReference, self: Transaction) -> Bool { ... }
    mint(redeemer: T, policy_id: PolicyId, self: Transaction) -> Bool { ... }
    withdraw(redeemer: T, account: Credential, self: Transaction) -> Bool { ... }
    publish(redeemer: T, cert: Certificate, self: Transaction) -> Bool { ... }
    vote(redeemer: T, voter: Voter, self: Transaction) -> Bool { ... }
    propose(redeemer: T, proposal: ProposalProcedure, self: Transaction) -> Bool { ... }
    else(_) { fail }
  }

CUSTOM TYPES — commas required after EVERY field (stdlib v3):
  pub type MyDatum {
    owner: VerificationKeyHash,
    deadline: Int,
    amount: Int,
  }

IMPORTS (slash style — never dot, imports must come first):
  use cardano/assets
  use cardano/transaction.{Transaction, OutputReference}
  use cardano/certificate.{Certificate}
  use cardano/governance.{Voter, ProposalProcedure}
  use aiken/collection/list
  use aiken/collection/dict
  use aiken/interval
  use aiken/math/rational

IMPORT RULES — always include these when using the types:
  Transaction, OutputReference → use cardano/transaction.{Transaction, OutputReference}
  InlineDatum                  → add to transaction import: .{Transaction, OutputReference, InlineDatum}
  PolicyId                     → use cardano/assets.{PolicyId}  OR prefix as assets.PolicyId
  Certificate                  → use cardano/certificate.{Certificate}
  Voter, ProposalProcedure     → use cardano/governance.{Voter, ProposalProcedure}

VERIFIED API PATTERNS:
  ADA check  : assets.lovelace_of(output.value) — NEVER output.assets.ada
  Signatures : list.has(self.extra_signatories, key) — NEVER self.signatures
  Time       : self.validity_range — type is Interval (NOT Interval<Int>)
  NFT check  : assets.quantity_of(value, policy_id, asset_name)
  Inputs     : transaction.find_input(self.inputs, ref)
  Ref inputs : transaction.find_input(self.reference_inputs, ref)
  InlineDatum: expect InlineDatum(raw) = output.datum — always import explicitly
  dict       : dict.to_pairs(d) — NEVER dict.to_list
  rational   : rational.new(n, d)

CERTIFICATE constructors (stdlib v3 exact names):
  RegisterCredential, UnregisterCredential, DelegateCredential
  RegisterAndDelegateCredential

REMOVED in stdlib v3 — NEVER generate:
  aiken/time | PosixTime        → use self.validity_range
  MintedValue                   → use Value
  VerificationKeyCredential     → use VerificationKey
  ScriptCredential              → use Script
  DeregisterCredential          → use UnregisterCredential
  Interval<Int>                 → use Interval (not generic)"""


def format_fn(examples):
    texts = []
    for ins, inp, out in zip(
        examples["instruction"],
        examples["input"],
        examples["output"],
    ):
        ins = (ins or "").strip()
        inp = (inp or "").strip()
        out = (out or "").strip()
        user_msg = f"{ins}\n\nInput:\n{inp}" if inp else ins
        text = (
            f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{user_msg}<|im_end|>\n"
            f"<|im_start|>assistant\n{out}<|im_end|>"
        )
        texts.append(text)
    return {"text": texts}


dataset  = dataset.map(format_fn, batched=True)
split    = dataset.train_test_split(test_size=0.05, seed=42)
train_ds = split["train"]
eval_ds  = split["test"]
print(f"Train: {len(train_ds)} | Eval: {len(eval_ds)}")

# ============================================
# 6) TRAINER
# ============================================
OUTPUT_DIR = "qwen35_4b_aiken_v23_v9"

trainer = SFTTrainer(
    model=model,
    processing_class=tokenizer,
    train_dataset=train_ds,
    eval_dataset=eval_ds,
    max_seq_length=MAX_SEQ_LENGTH,
    packing=False,
    callbacks=[EarlyStoppingCallback(early_stopping_patience=3)],
    args=SFTConfig(
        per_device_train_batch_size=4,
        gradient_accumulation_steps=8,
        warmup_steps=50,
        num_train_epochs=7,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        bf16=True,
        fp16=False,
        logging_steps=1,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=50,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        optim="adamw_torch",
        weight_decay=0.01,
        seed=3407,
        output_dir=OUTPUT_DIR,
        report_to="none",
    ),
)

steps_per_epoch = len(train_ds) // (4 * 8)
print(f"Steps por epoch : {steps_per_epoch}")
print(f"Total steps max : {steps_per_epoch * 7}  (early stopping patience=3)")

# ============================================
# 7) ENTRENAR
# ============================================
print("Entrenando cardano-dev v9 — Qwen3.5-4B (dataset v22: 3,748 ej, 7 épocas max)...")
trainer.train()

print(f"\nMejor checkpoint : {trainer.state.best_model_checkpoint}")
print(f"Mejor val loss   : {trainer.state.best_metric:.6f}")

# ============================================
# 8) GUARDAR LORA + GGUF
# ============================================
LORA_DIR = "qwen35_4b_aiken_v23_v9_lora"
GGUF_DIR = "qwen35_4b_aiken_v23_v9_gguf"

model.save_pretrained(LORA_DIR)
tokenizer.save_pretrained(LORA_DIR)
print(f"LoRA guardado en {LORA_DIR}")

print("Exportando GGUF Q4_K_M...")
model.save_pretrained_gguf(
    GGUF_DIR,
    tokenizer,
    quantization_method="q4_k_m",
)
print(f"GGUF guardado en {GGUF_DIR}")

# ============================================
# 9) GUARDAR EN DRIVE
# ============================================
from google.colab import drive
import shutil

drive.mount("/content/drive")

gguf_candidates = glob.glob(f"/content/{GGUF_DIR}/**/*.Q4_K_M.gguf", recursive=True)
assert gguf_candidates, f"No se encontró Q4_K_M.gguf en {GGUF_DIR} — revisá el directorio"
gguf_src = gguf_candidates[0]
print(f"GGUF encontrado: {gguf_src}")

drive_gguf = "/content/drive/MyDrive/cardano-dev-9.0-v23-q4_k_m.gguf"
drive_lora = "/content/drive/MyDrive/cardano-dev-9.0-v23-lora"

shutil.copy(gguf_src, drive_gguf)
shutil.copytree(f"/content/{LORA_DIR}", drive_lora, dirs_exist_ok=True)

print(f"GGUF  → {drive_gguf}")
print(f"LoRA  → {drive_lora}")
print("Todo guardado en Drive.")
