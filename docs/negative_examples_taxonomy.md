# Taxonomía de conocimiento negativo — Dataset Aiken/Cardano

Este documento define el formato canónico, la taxonomía de bugs frecuentes, y el protocolo de conversión para ejemplos de entrenamiento basados en conocimiento negativo (errores comunes en Aiken v3).

---

## 1. Formato canónico de training

### Template general

Cada ejemplo de training con conocimiento negativo sigue la "Opción C": el asistente escribe código correcto e incluye comentarios defensivos que explican qué no hacer y por qué. El formato canónico es:

```
{"role": "user", "content": "<pregunta o tarea de programación Aiken>"}
{"role": "assistant", "content": "<código correcto con comentarios defensivos inline>"}
```

Los comentarios defensivos deben:
- Identificar el error por su nombre de taxonomía entre paréntesis o en el comentario.
- Explicar el modelo mental erróneo que lleva al bug.
- Mostrar la forma correcta en el mismo bloque de código.

### Ejemplo completo — `prop_undercollateralized_unhealthy` convertido a formato de training

**Archivo fuente:** `25d_liquidation_partial.ak`
**Fail test de origen:**
```aiken
test prop_undercollateralized_unhealthy(
  debt via fuzz.int_between(101, 500),
) fail {
  // collateral=1, target_ratio=150: 1*100=100 < debt*150 for any debt>0
  expect healthy_after_repay(1, debt, 0, 150)
}
```

**Ejemplo de training resultante:**

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Escribe un validador de liquidación parcial en Aiken que incluya una función `healthy_after_repay` y un property test que verifique que posiciones sin colateral suficiente siempre se consideran no sanas cuando no se repaga nada."
    },
    {
      "role": "assistant",
      "content": "```aiken\nuse aiken/fuzz\n\n/// Devuelve True si la posición es sana después de un repago.\n///\n/// IMPORTANTE: usar `new_debt >= 0`, NO `new_debt > 0`.\n/// El error `unhealthy_zero_debt` ocurre cuando se escribe `new_debt > 0`:\n/// eso rechaza un repago completo (debt == repay, new_debt == 0),\n/// que es el estado más sano posible. La condición correcta es >= 0.\nfn healthy_after_repay(collateral: Int, debt: Int, repay: Int, target_ratio: Int) -> Bool {\n  let new_debt = debt - repay\n  // >= 0, no > 0: deuda cero significa posición completamente repagada (válido)\n  new_debt >= 0 && collateral * 100 >= new_debt * target_ratio\n}\n\n/// Este test tiene la anotación `fail` porque healthy_after_repay DEBE devolver False\n/// cuando collateral=1, repay=0 y debt>100 con target_ratio=150.\n/// Si la función devuelve True para esos valores, el validador tiene un bug.\ntest prop_undercollateralized_unhealthy(\n  debt via fuzz.int_between(101, 500),\n) fail {\n  // collateral=1, target_ratio=150: 1*100=100 < debt*150 para todo debt>0\n  // expect debe fallar — la posición es insalubre, no debería pasar\n  expect healthy_after_repay(1, debt, 0, 150)\n}\n```"
    }
  ]
}
```

**Notas de conversión:**
- El `fail` en el nombre del test indica que `expect` debe fallar: el test pasa si y solo si la expresión lanza un error. El comentario defensivo explica esto para que el modelo aprenda la semántica.
- El comentario sobre `>= 0` vs `> 0` enseña el bug `unhealthy_zero_debt` directamente en contexto.

---

## 2. Taxonomía de bugs Aiken v3

### Bug 1 — `always_true`

**Modelo mental erróneo:** "El handler `else` puede devolver `True` como fallback seguro; si nadie debería llegar aquí, no importa."

**Snippet incorrecto:**
```aiken
validator my_validator {
  spend(datum, redeemer, ref, self) { check_logic(datum, redeemer, self) }
  else(_) { True }  // BUG: cualquier redeemer no reconocido pasa sin validación
}
```

**Comentario defensivo correcto:**
```aiken
validator my_validator {
  spend(datum, redeemer, ref, self) { check_logic(datum, redeemer, self) }
  // SIEMPRE usar `fail` en el handler else, nunca True.
  // `else(_) { True }` convierte el else en una puerta trasera:
  // cualquier transacción que no encaje en los handlers declarados
  // pasaría la validación sin ningún chequeo.
  else(_) { fail }
}
```

---

### Bug 2 — `double_satisfaction`

**Modelo mental erróneo:** "Si verifico que el datum es correcto, estoy verificando el output correcto."

**Snippet incorrecto:**
```aiken
validator swap {
  spend(datum: Option<SwapDatum>, redeemer: SwapRedeemer, _ref, self) {
    expect Some(d) = datum
    // BUG: no verifica que el output enviado al vendedor corresponde
    // a ESTE input específico — un atacante puede satisfacer dos swaps
    // con un único output, robando fondos del segundo.
    let paid = value_paid_to(self.outputs, d.seller)
    paid >= d.min_receive
  }
  else(_) { fail }
}
```

**Comentario defensivo correcto:**
```aiken
validator swap {
  spend(datum: Option<SwapDatum>, redeemer: SwapRedeemer, own_ref: OutputReference, self) {
    expect Some(d) = datum
    // Para evitar double satisfaction: filtrar outputs por un ID único
    // vinculado a este input (e.g., NFT de identificación o el propio OutRef).
    // Sin esto, un solo output puede "satisfacer" múltiples inputs simultáneamente.
    let own_input = find_input(self.inputs, own_ref)
    let tagged_output = find_output_with_tag(self.outputs, own_ref)
    let paid = value_of(tagged_output)
    paid >= d.min_receive
  }
  else(_) { fail }
}
```

---

### Bug 3 — `missing_signature_check`

**Modelo mental erróneo:** "Si el datum contiene el owner, con verificar el datum es suficiente para autenticar."

**Snippet incorrecto:**
```aiken
validator owner_only {
  spend(datum: Option<OwnerDatum>, _redeemer, _ref, _self) {
    expect Some(d) = datum
    // BUG: solo verifica que el datum tiene un owner, no que
    // el owner firmó la transacción. Cualquiera puede gastar el UTXO
    // si conoce el datum.
    d.owner != #""
  }
  else(_) { fail }
}
```

**Comentario defensivo correcto:**
```aiken
use aiken/collection/list

validator owner_only {
  spend(datum: Option<OwnerDatum>, _redeemer, _ref, self: Transaction) {
    expect Some(d) = datum
    // SIEMPRE verificar que el owner está en extra_signatories.
    // Verificar el campo del datum no autentica nada — el datum es público
    // y cualquiera puede construir una transacción con ese datum.
    list.any(self.extra_signatories, fn(sig) { sig == d.owner })
  }
  else(_) { fail }
}
```

---

### Bug 4 — `wrong_datum_unwrap`

**Modelo mental erróneo:** "Puedo hacer pattern match directo sobre el datum Option; si falla es un error del caller."

**Snippet incorrecto:**
```aiken
validator my_validator {
  spend(datum: Option<MyDatum>, redeemer, _ref, self) {
    // BUG: pattern match exhaustivo omitido — en Aiken v3 el datum
    // puede ser None si el UTXO no tiene datum inline. Sin `expect`,
    // el compilador puede aceptar código que ignora el caso None
    // dependiendo de cómo esté estructurado el match.
    when datum is {
      Some(d) -> check(d, redeemer, self)
      // None no manejado: el validador podría compilar pero el comportamiento
      // en runtime es indefinido o pasa silenciosamente.
    }
  }
  else(_) { fail }
}
```

**Comentario defensivo correcto:**
```aiken
validator my_validator {
  spend(datum: Option<MyDatum>, redeemer, _ref, self) {
    // SIEMPRE usar `expect Some(d) = datum` para unwrap del datum.
    // Esto hace explícito que la transacción DEBE fallar si no hay datum inline.
    // Un pattern match incompleto puede introducir comportamiento inesperado.
    expect Some(d) = datum
    check(d, redeemer, self)
  }
  else(_) { fail }
}
```

---

### Bug 5 — `missing_import`

**Modelo mental erróneo:** "Las funciones de stdlib están disponibles globalmente; no necesito importar el módulo."

**Snippet incorrecto:**
```aiken
// BUG: `list.any` se usa sin importar el módulo.
// Aiken v3 NO tiene imports implícitos de stdlib — todo módulo
// debe declararse con `use`. El compilador dará un error de nombre
// no encontrado, pero el modelo puede generar código sin el import
// si no fue entrenado correctamente.

validator sig_check {
  spend(datum: Option<Datum>, _r, _ref, self: Transaction) {
    expect Some(d) = datum
    list.any(self.extra_signatories, fn(s) { s == d.owner })  // falla en compilación
  }
  else(_) { fail }
}
```

**Comentario defensivo correcto:**
```aiken
// SIEMPRE incluir el import antes de usar funciones de módulos stdlib.
// Módulos de uso frecuente en validators:
//   use aiken/collection/list          -- list.any, list.filter, list.find
//   use aiken/collection/dict          -- dict.size, dict.to_pairs
//   use cardano/transaction.{Transaction, OutputReference}
//   use cardano/assets                 -- assets.tokens, assets.quantity_of
use aiken/collection/list

validator sig_check {
  spend(datum: Option<Datum>, _r, _ref, self: Transaction) {
    expect Some(d) = datum
    list.any(self.extra_signatories, fn(s) { s == d.owner })
  }
  else(_) { fail }
}
```

---

### Bug 6 — `multi_token_mint`

**Modelo mental erróneo:** "Si verifico que la cantidad acuñada no es cero, el mint policy es seguro."

**Contexto:** Extraído de `18c_vault_multi_token_guard.ak`. La función `valid_vault_mint` es la referencia correcta.

**Snippet incorrecto:**
```aiken
use cardano/assets

validator vault_mint {
  mint(_redeemer: Data, policy_id: PolicyId, self: Transaction) {
    let minted_tokens = assets.tokens(self.mint, policy_id)
    // BUG: solo verifica que hay al menos un token con cantidad != 0,
    // pero no verifica cuántos token names distintos se acuñan.
    // Un atacante puede acuñar "vault_token" Y "admin_token" en la misma
    // transacción; si el vault solo espera uno, el segundo pasa sin control.
    when dict.to_pairs(minted_tokens) is {
      [Pair(_, qty)] -> qty != 0
      _ -> False
    }
    // Falta: dict.size(minted_tokens) == 1
  }
  else(_) { fail }
}
```

**Comentario defensivo correcto:**
```aiken
use aiken/collection/dict
use cardano/assets.{PolicyId}
use cardano/transaction.{Transaction}

fn valid_vault_mint(tokens: dict.Dict<AssetName, Int>) -> Bool {
  // Dos condiciones OBLIGATORIAS para un mint policy de vault:
  // 1. Solo UN token name por transacción (evita acuñar tokens no autorizados).
  // 2. La cantidad es distinta de cero (evita transacciones vacías o burns).
  dict.size(tokens) == 1 && when dict.to_pairs(tokens) is {
    [Pair(_, qty)] -> qty != 0
    _ -> False
  }
}

validator vault_mint {
  mint(_redeemer: Data, policy_id: PolicyId, self: Transaction) {
    let minted_tokens = assets.tokens(self.mint, policy_id)
    // NUNCA omitir la verificación de dict.size — un mint policy
    // sin ella permite multi-token mints bajo la misma policy.
    valid_vault_mint(minted_tokens)
  }
  else(_) { fail }
}
```

---

### Bug 7 — `unhealthy_zero_debt`

**Modelo mental erróneo:** "Una deuda de cero es un estado extraño que no debería ocurrir; usar `> 0` es más seguro que `>= 0`."

**Contexto:** Extraído de `25d_liquidation_partial.ak`.

**Snippet incorrecto:**
```aiken
fn healthy_after_repay(collateral: Int, debt: Int, repay: Int, target_ratio: Int) -> Bool {
  let new_debt = debt - repay
  // BUG: `new_debt > 0` rechaza el repago completo (new_debt == 0).
  // Si alguien repaga toda la deuda, new_debt = 0, la condición falla,
  // y el validador bloquea una operación completamente legítima.
  new_debt > 0 && collateral * 100 >= new_debt * target_ratio
}
```

**Comentario defensivo correcto:**
```aiken
fn healthy_after_repay(collateral: Int, debt: Int, repay: Int, target_ratio: Int) -> Bool {
  let new_debt = debt - repay
  // CORRECTO: `new_debt >= 0`.
  // new_debt == 0 significa deuda completamente saldada — el estado más sano.
  // new_debt > 0 bloquearía repagos completos, creando un grifo de fondos:
  // el deudor no podría recuperar su colateral nunca.
  new_debt >= 0 && collateral * 100 >= new_debt * target_ratio
}
```

---

### Bug 8 — `off_by_one_ratio`

**Modelo mental erróneo:** "El ratio de colateralización es un porcentaje, así que multiplico por 100 y divido por el ratio."

**Snippet incorrecto:**
```aiken
fn is_overcollateralized(collateral: Int, debt: Int, min_ratio: Int) -> Bool {
  // BUG: la comparación está invertida.
  // Si min_ratio=150 (150%), la condición correcta es:
  //   collateral * 100 >= debt * min_ratio
  // El bug común es escribirlo al revés:
  collateral * min_ratio >= debt * 100
  // Esto acepta posiciones subcolateralizadas cuando min_ratio > 100.
}
```

**Comentario defensivo correcto:**
```aiken
fn is_overcollateralized(collateral: Int, debt: Int, min_ratio: Int) -> Bool {
  // Para un ratio del 150%: el colateral debe valer al menos 1.5x la deuda.
  // Forma sin división (evita truncamiento entero):
  //   collateral * 100 >= debt * min_ratio
  // Mnemónico: "100 partes del colateral >= min_ratio partes de la deuda"
  collateral * 100 >= debt * min_ratio
}
```

---

### Bug 9 — `stale_datum_reuse`

**Modelo mental erróneo:** "El datum del output de continuación puede ser cualquier cosa válida; el validador ya verificó el datum del input."

**Snippet incorrecto:**
```aiken
validator stateful {
  spend(datum: Option<State>, redeemer: Action, _ref, self: Transaction) {
    expect Some(s) = datum
    let new_value = apply_action(s, redeemer)
    // BUG: no verifica que el output de continuación tiene el datum actualizado.
    // El estado nunca cambia en la cadena — cualquier acción "pasa" pero
    // el estado vuelve al mismo datum original en el siguiente UTXO.
    value_sent_to_script(self.outputs) >= s.locked_value
  }
  else(_) { fail }
}
```

**Comentario defensivo correcto:**
```aiken
validator stateful {
  spend(datum: Option<State>, redeemer: Action, _ref, self: Transaction) {
    expect Some(s) = datum
    let new_state = apply_action(s, redeemer)
    // SIEMPRE verificar que el output de continuación lleva el datum NUEVO.
    // Sin esta verificación, el estado on-chain no avanza nunca,
    // convirtiendo el validator en un honeypot o en código muerto.
    let cont_output = find_script_output(self.outputs)
    let cont_datum = inline_datum(cont_output)
    cont_datum == new_state && value_of(cont_output) >= s.locked_value
  }
  else(_) { fail }
}
```

---

## 3. Protocolo de conversión (paso a paso)

### Paso 1 — Revisión manual (humano)

Antes de delegar a Claude, el revisor humano debe verificar:

1. **Identificar el tipo de ejemplo negativo:** ¿Es un `fail` test fuzz, un snippet de código incorrecto documentado, o un bug encontrado en auditoría?
2. **Clasificar en la taxonomía:** Asignar el nombre de bug de la sección 2. Si no encaja, proponer un nombre nuevo siguiendo la convención `snake_case`.
3. **Verificar que el código "incorrecto" compila en la versión de Aiken objetivo** (actualmente v3 con `cardano/transaction`, `cardano/assets`). Un snippet que ni siquiera compila no es útil como ejemplo negativo; es mejor partir del correcto y introducir el error específico.
4. **Confirmar que el error es explotable o tiene consecuencia real:** bugs de estilo o naming no son conocimiento negativo de seguridad.

### Paso 2 — Delegación a Claude

Una vez clasificado, se puede delegar a Claude la tarea de:

1. Escribir el comentario defensivo inline según el template de la sección 1.
2. Generar variantes del ejemplo con distintos nombres de variables para enriquecer el dataset.
3. Redactar la pregunta del usuario (`"role": "user"`) que naturalmente llevaría a escribir ese código, sin mencionar el bug explícitamente.

**Prompt recomendado para Claude:**
```
Dado este código Aiken incorrecto con el bug `{nombre_bug}`:

{snippet_incorrecto}

Escribe la versión correcta con comentarios defensivos inline que:
1. Nombren el bug entre paréntesis en el primer comentario relevante.
2. Expliquen el modelo mental erróneo en 1-2 líneas.
3. Muestren la forma correcta con un comentario de una línea.
No cambies la estructura del validator, solo corrige el bug y agrega comentarios.
```

### Paso 3 — Formateo como ejemplo de training

1. Envolver en el schema `{"messages": [{"role": "user", ...}, {"role": "assistant", ...}]}`.
2. Escapar los backticks internos si el formato final es JSONL.
3. Agregar al archivo `dataset_vXX.jsonl` con el campo `"source": "negative_taxonomy"` para trazabilidad.
4. Ejecutar `benchmark.py` o el script de audit correspondiente para verificar que el ejemplo pasa la validación de formato.

### Paso 4 — Revisión final (humano)

- Releer el comentario defensivo: ¿es preciso? ¿No introduce confusión sobre casos legítimos?
- Verificar que la pregunta del usuario es plausible (alguien real podría hacerla).
- Si el bug viene de un `fail` test fuzz, asegurarse de que el comentario explica la semántica de `fail` en Aiken.

---

## 4. Ejemplos completos antes/después

### Ejemplo A — `multi_token_mint` (18c_vault_multi_token_guard.ak)

**Antes (código con bug):**
```aiken
use cardano/assets
use cardano/transaction.{Transaction}
use cardano/assets.{PolicyId}

validator vault_bad {
  mint(_redeemer: Data, policy_id: PolicyId, self: Transaction) {
    let minted_tokens = assets.tokens(self.mint, policy_id)
    // Solo verifica cantidad != 0, ignora cuántos token names hay
    when dict.to_pairs(minted_tokens) is {
      [Pair(_, qty)] -> qty != 0
      _ -> False
    }
  }
  else(_) { fail }
}
```

**Después (ejemplo de training completo):**

Pregunta del usuario:
> "Escribe un mint validator para un vault de Cardano que rechace transacciones que intenten acuñar más de un token name bajo la misma policy, y agrega un property test que verifique que un solo token con cantidad positiva es válido."

Respuesta del asistente:
```aiken
/// Vault rejects mints that touch more than one token name
use aiken/collection/dict
use aiken/fuzz
use cardano/assets.{AssetName, PolicyId}
use cardano/fuzz as cfuzz
use cardano/transaction.{Transaction}

/// Verifica que solo se acuña UN token name bajo esta policy.
///
/// BUG FRECUENTE (multi_token_mint): omitir `dict.size(tokens) == 1`.
/// Sin esta verificación, una sola transacción puede acuñar "vault_token"
/// y "admin_token" simultáneamente bajo la misma policy, sin control adicional.
fn single_token_only(tokens: dict.Dict<AssetName, Int>) -> Bool {
  // dict.size == 1 garantiza exactamente un token name, no "al menos uno"
  dict.size(tokens) == 1
}

fn non_zero_qty(tokens: dict.Dict<AssetName, Int>) -> Bool {
  when dict.to_pairs(tokens) is {
    [Pair(_, qty)] -> qty != 0
    _ -> False
  }
}

fn valid_vault_mint(tokens: dict.Dict<AssetName, Int>) -> Bool {
  single_token_only(tokens) && non_zero_qty(tokens)
}

validator vault_multi_token_guard {
  mint(_redeemer: Data, policy_id: PolicyId, self: Transaction) {
    let minted_tokens = assets.tokens(self.mint, policy_id)
    let only_one = single_token_only(minted_tokens)
    let qty_ok = non_zero_qty(minted_tokens)
    // Ambas condiciones son necesarias — ninguna sola es suficiente
    only_one && qty_ok
  }
  else(_) { fail }
}

/// Property test: un único token con cantidad positiva siempre es válido.
test prop_single_nonzero_valid(
  vals via fuzz.both(cfuzz.asset_name(), fuzz.int_at_least(1)),
) {
  let (name, qty) = vals
  let tokens = dict.empty |> dict.insert(name, qty)
  valid_vault_mint(tokens)
}

/// Este test falla intencionalmente: cantidad cero debe ser rechazada.
/// La anotación `fail` significa que `expect` DEBE lanzar un error.
/// Si valid_vault_mint devolviera True para qty=0, el test fallaría.
test prop_zero_qty_rejected(name via cfuzz.asset_name()) fail {
  let tokens = dict.empty |> dict.insert(name, 0)
  expect valid_vault_mint(tokens)
}
```

---

### Ejemplo B — `unhealthy_zero_debt` (25d_liquidation_partial.ak)

**Antes (código con bug):**
```aiken
fn healthy_after_repay(collateral: Int, debt: Int, repay: Int, target_ratio: Int) -> Bool {
  let new_debt = debt - repay
  // BUG unhealthy_zero_debt: new_debt > 0 bloquea repago completo
  new_debt > 0 && collateral * 100 >= new_debt * target_ratio
}
```

**Después (ejemplo de training completo):**

Pregunta del usuario:
> "Implementa un validador de liquidación parcial en Aiken con una función que verifique si una posición es sana después de un repago, y un property test fuzz que confirme que posiciones con colateral insuficiente (collateral=1, target_ratio=150) nunca son sanas sin repago."

Respuesta del asistente:
```aiken
/// Partial liquidation: liquidate only enough to restore health
use aiken/fuzz
use aiken/collection/list
use cardano/transaction.{Transaction, OutputReference}

/// Calcula el mínimo repago necesario para restaurar la salud de la posición.
fn min_repay_to_restore(collateral: Int, debt: Int, target_ratio: Int) -> Int {
  let max_debt = collateral * 100 / target_ratio
  if debt > max_debt { debt - max_debt } else { 0 }
}

/// Devuelve True si la posición es sana después del repago dado.
///
/// CORRECCIÓN CRÍTICA (unhealthy_zero_debt): la condición es `new_debt >= 0`,
/// NO `new_debt > 0`. El error `> 0` rechaza el repago completo:
/// cuando repay == debt, new_debt = 0, que es el estado más sano posible.
/// Con `> 0`, el deudor nunca podría recuperar su colateral completamente.
fn healthy_after_repay(collateral: Int, debt: Int, repay: Int, target_ratio: Int) -> Bool {
  let new_debt = debt - repay
  // >= 0: deuda cero es válida (posición completamente saldada)
  new_debt >= 0 && collateral * 100 >= new_debt * target_ratio
}

pub type LiquidationDatum {
  collateral: Int,
  debt: Int,
  target_ratio: Int,
  owner: ByteArray,
}

pub type LiquidationRedeemer {
  repay_amount: Int,
}

validator partial_liquidation {
  spend(datum: Option<LiquidationDatum>, redeemer: LiquidationRedeemer, _ref: OutputReference, self: Transaction) {
    expect Some(d) = datum
    let repay = redeemer.repay_amount
    let min_repay = min_repay_to_restore(d.collateral, d.debt, d.target_ratio)
    let position_restored = healthy_after_repay(d.collateral, d.debt, repay, d.target_ratio)
    let repay_sufficient = repay >= min_repay
    // missing_signature_check: SIEMPRE verificar extra_signatories, no solo el datum
    let signed_by_owner = list.any(self.extra_signatories, fn(sig) { sig == d.owner })
    repay_sufficient && position_restored && signed_by_owner
  }
  else(_) { fail }
}

/// Cuando el colateral es 1 y target_ratio=150, ningún debt>100 sin repago
/// puede ser sano: 1*100=100 < debt*150 para todo debt>=101.
test prop_no_repay_needed_when_healthy(
  vals via fuzz.both(fuzz.int_between(200, 500), fuzz.int_between(1, 100)),
) {
  let (collateral, debt) = vals
  min_repay_to_restore(collateral, debt, 150) == 0
}

/// Test con anotación `fail`: healthy_after_repay DEBE devolver False aquí.
/// Si devolviera True para (collateral=1, repay=0, debt>100), el validator
/// permitiría que posiciones insalubres pasen sin liquidación — un bug crítico.
test prop_undercollateralized_unhealthy(
  debt via fuzz.int_between(101, 500),
) fail {
  // collateral=1, target_ratio=150: 1*100=100 < debt*150 para todo debt>100
  expect healthy_after_repay(1, debt, 0, 150)
}
```

---

*Documento generado para el proyecto Cardano AI Dataset — fase de knowledge negative examples. Fecha de referencia: 2026-04-04.*
