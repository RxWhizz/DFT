# Metodología física de PEROVOWL

**Informe técnico.** Explica, en términos físicos y no computacionales, por
qué el pipeline está construido como está: qué mide cada etapa, qué
aproximación introduce, y qué consecuencia física tiene esa aproximación.
Cierra con una auditoría de los puntos donde la aproximación deja de ser
razonable — no todo lo que el código hace tiene sentido físico incondicional,
y es más útil decirlo aquí que dejarlo implícito.

Reemplaza la versión anterior de este documento (tablas de equivalencia
VASP↔GPAW y comandos de α-CsPbI₃), cuyo contenido útil se conserva en la
sección 6.

---

## 1. El objetivo, en física de detalle balance

Todo el pipeline persigue un solo número: un semiconductor con bandgap `Eg`
tal que, iluminado por el espectro solar terrestre, convierta la mayor
fracción posible de esa luz en electricidad. Ese óptimo no es una intuición —
sale del límite de **Shockley–Queisser**: el techo termodinámico de
eficiencia de una unión simple, bajo la hipótesis de que la única vía de
recombinación es la radiativa (la más favorable posible).

El cálculo compara dos flujos de fotones bajo el espectro AM1.5G (ASTM
G173-03, la irradiancia solar terrestre estándar tras atravesar 1.5 masas de
atmósfera):

- **Fotones absorbidos**: todos los del espectro con energía ≥ `Eg` generan
  un par electrón-hueco. Cada uno entrega como máximo `Eg` de energía útil —
  el exceso sobre `Eg` se termaliza como calor en picosegundos, no es
  recuperable.
- **Recombinación radiativa**: en equilibrio, un absorbedor a temperatura de
  la célula también *emite* fotones térmicos según su propio bandgap (ley de
  Planck truncada en `Eg`). Ese flujo de emisión fija la corriente de
  saturación mínima posible y, con ella, el voltaje máximo alcanzable.

Balancear ambos términos da una curva de eficiencia límite vs. `Eg` con
máximo ancho y plano entre **1.1 y 1.6 eV** (pico ≈ 33 % cerca de 1.34 eV para
AM1.5G). Fuera de esa banda se pierde eficiencia por dos motivos físicos
distintos y opuestos: `Eg` bajo absorbe casi todo el espectro pero termaliza
mucha energía por fotón; `Eg` alto conserva energía por fotón pero deja sin
absorber la mitad roja del espectro. La ventana fotovoltaica del cribado,
`[1.1, 1.8]` eV, es una traducción directa de esa curva — no un rango elegido
por conveniencia. `src/dft_cspbi3/analysis/sq_limit.py` implementa el cálculo
completo con la tabla ASTM real, no una aproximación analítica de la curva.

Dos magnitudes accesorias completan el cuadro fotovoltaico y aparecen como
predicciones ML en el cribado:

- **Energía de enlace del excitón** (`eps_inf_pred`, `meff_e/h_pred`): en el
  modelo hidrogenoide de Wannier–Mott, `E_b ≈ 13.6 eV · (μ*/m₀) / ε_r²`, con
  `μ*` la masa reducida electrón-hueco y `ε_r` la constante dieléctrica de
  alta frecuencia. Un excitón fuertemente ligado (`E_b ≫ k_BT ≈ 25 meV` a
  temperatura ambiente) recombina antes de disociarse en portadores libres;
  las perovskitas de haluro son atractivas precisamente porque su alta
  constante dieléctrica (apantallamiento iónico-electrónico, más efectos de
  polarón grande) mantiene `E_b` en el rango de unos pocos a unas decenas de
  meV pese a ser materiales bastante iónicos.
- **Masa efectiva** (`meff_e_pred_m0`, `meff_h_pred_m0`): la curvatura de la
  banda en el extremo (`1/m* = ℏ⁻² ∂²E/∂k²`) fija cuánto se dispersan los
  portadores fotogenerados, es decir, su movilidad. Bandas planas (masa
  efectiva grande) son malas para el transporte aunque el bandgap sea
  perfecto.

## 2. Nivel 0 — Geometría: ¿puede existir la jaula ABX₃?

Antes de gastar un solo electrón-voltio de cómputo, se descarta lo que no
puede ni empaquetar como perovskita. Dos razones geométricas, ambas del
modelo de esferas duras en contacto de Goldschmidt (1926):

**Factor de tolerancia** `t = (r_A + r_X) / (√2·(r_B + r_X))`. Se deriva de
imponer que, en la celda cúbica ideal, el catión A toque a los aniones X a lo
largo de la diagonal de cara mientras el catión B los toca a lo largo de la
arista — dos condiciones geométricas simultáneas que solo son compatibles
exactamente en `t = 1`. `t < 1` deja al catión A "flotando" en una jaula
demasiado grande, que la estructura resuelve rotando/inclinando los octaedros
BX₆ (bajando la simetría, cúbico → tetragonal → ortorrómbico); `t > 1`
estira la jaula hasta romper el empaquetamiento de esquinas compartidas hacia
politipos hexagonales. El rango aceptado aquí, `[0.80, 1.10]`
(`src/buho/filters/physical_filters.py`), es más ancho que el `[0.8, 1.0]`
clásico de óxidos: los haluros son aniones más blandos y polarizables, y la
literatura de perovskitas de haluro documenta tolerancia geométrica algo
mayor en el extremo superior.

**Factor octaédrico** `μ = r_B / r_X`. Es la condición aparte de que el
catión B quepa *dentro* del octaedro de seis aniones X sin que estos se
toquen entre sí ni dejen a B suelto — estabilidad del octaedro BX₆ en sí,
independiente de cómo empaquete con A. Rango aceptado: `[0.40, 0.90]`.

Ambos son condiciones **necesarias**, no suficientes: descartan lo
geométricamente absurdo, pero no dicen si la fase que de verdad cristaliza a
temperatura ambiente es la perovskita cúbica que el resto del pipeline
asume. La sección 7 cuantifica por qué eso importa.

## 3. Nivel 1 — Surrogate: bandgap desde la composición

Antes de construir una sola celda, un ensemble RandomForest+GradientBoosting
predice `Eg` y su incertidumbre `σ` a partir de descriptores derivados solo
de la composición: radios y electronegatividades efectivos (mezcla lineal
tipo Vegard sobre cada sitio mixto), el propio `t` y `μ`, y una diferencia de
electronegatividad B–X como proxy de carácter iónico/covalente del enlace —
el enlace más covalente típicamente da bandas más dispersivas y bandgaps más
pequeños, que es la tendencia química que el modelo tiene que aprender.

El cribado no descarta por el valor puntual de `Eg`, sino por
`Eg ± σ_k·σ` contra la ventana: un candidato con `Eg = 0.95 ± 0.18` eV sigue
siendo plausible frente al límite de 1.1 eV. Esto es, en esencia, análisis de
propagación de incertidumbre — no se tira un dato porque su estimación
puntual caiga fuera de la banda de interés si su barra de error la alcanza.

**Qué aprende de verdad el surrogate** depende de contra qué se reentrena
(sección 5): en este pipeline, contra el bandgap DFT de un solo punto sobre
la celda cúbica ideal (sección 5), no contra el bandgap experimental. Eso
tiene una consecuencia física directa que se trata en la sección 7.

## 4. Nivel 2 — MLFF: ¿es termodinámicamente favorable?

MEGNet y M3GNet (redes de grafos entrenadas sobre datos de Materials
Project) estiman la energía de formación `Eform` desde la estructura 3D
construida (sección 5), no solo la composición — ya usan geometría, aunque
sea la idealizada. `Eform < 0` respecto a los elementos es condición
termodinámica necesaria para que el compuesto exista sin descomponerse
espontáneamente en sus elementos; el umbral por defecto es
`Eform_max = 0.20 eV/átomo` (con la misma holgura de incertidumbre `σ_k` que
el Tier 1, vía la discrepancia MEGNet↔M3GNet como proxy de error del
ensemble).

Dos advertencias físicas, ambas explícitas en el propio código del
proyecto, no descubiertas aquí:

- MEGNet/M3GNet son modelos **generales**, entrenados mayoritariamente sobre
  óxidos e inorgánicos de Materials Project — no específicamente sobre
  perovskitas de haluro, que tienen enlace más blando y más iónico. Es
  extrapolación, no interpolación. La Fase 2A del proyecto
  (`src/buho/phase2_force/`) existe explícitamente para reemplazarlos por un
  potencial MACE afinado con energías y fuerzas DFT de esta propia familia
  química.
- `Eform` **respecto a los elementos** dice "termodinámicamente favorable
  formarse", no "esta es la fase que gana". Un compuesto puede tener `Eform`
  negativo y aun así perder frente a un politipo competidor no-perovskita con
  `Eform` más negativo todavía — exactamente el caso de la sección 7.

## 5. La verificación DFT del cribado: qué mide realmente

Los candidatos que sobreviven los tres tiers llegan a un cálculo GPAW real,
cuya etiqueta (`Eg_target_eV`) es la que retroalimenta al surrogate en cada
ronda del protocolo autónomo. Los parámetros
(`config/generator.yaml`, `scripts/buho_relax_runner.py`) están elegidos con
un criterio físico explícito: la etiqueta es un **ranking relativo con
metodología consistente**, no un número absoluto de referencia. Eso justifica
cada recorte:

- **PBE, `ecut = 300 eV`, sin +D3, sin SOC.** El funcional PBE (GGA
  semi-local) subestima bandgaps de forma sistemática por el error de
  autointeracción/deslocalización: al no cancelar del todo la interacción de
  un electrón consigo mismo, el funcional deslocaliza la densidad de más de
  lo físico y cierra la brecha entre bandas. Es un error conocido, no un
  fallo del cálculo — la caracterización profunda (sección 6) lo corrige con
  HSE06 y SOC. Aquí se acepta a cambio de que un punto cueste ~1× en vez de
  ~60× (HSE06+SOC), factor que multiplicado por decenas de miles de
  candidatos por ronda es la diferencia entre horas y meses.

- **Muestreo Γ-only en superceldas, `[2,2,2]` en celda unidad — y es una
  elección elegante, no un recorte tosco.** En una perovskita cúbica ABX₃,
  los extremos de banda de valencia y conducción típicamente caen en el
  punto R `(½,½,½)` de la zona de Brillouin primitiva, no en Γ. Al construir
  una supercelda 2×2×2, la zona de Brillouin se pliega: el punto Γ de la
  supercelda es exactamente el punto R (junto con X y M) de la celda
  primitiva plegado sobre sí mismo. Muestrear solo Γ en la supercelda **sí
  captura el extremo de banda relevante**, sin necesidad de una malla densa.
  Para la celda unidad sin plegar, una malla `[2,2,2]` centrada en Γ
  (`gamma=True`) incluye exactamente los puntos `{0, ½}` en cada eje — Γ, X,
  M y R — así que también resuelve R directamente. El recorte de coste real
  no está en la malla k, sino en no refinarla más allá de este mínimo
  suficiente.

- **Punto único (`max_steps=0`), sin relajar posiciones ni celda.** La
  estructura de partida es una celda cúbica ideal cuya constante de red sale
  de una suma de radios iónicos (`a₀ = 2·(r_B+r_X)`, el enlace B–X estirado a
  lo largo de la arista) — no de una minimización de energía. El cálculo
  reporta la energía electrónica exacta *de esa geometría*, con fuerzas
  netas no nulas: no es un mínimo de energía, y no debe leerse como tal.
  Consecuencia física directa: cualquier física que dependa de que los
  átomos se muevan desde la posición ideal —inclinación de los octaedros,
  relajación local del entorno alrededor de un dopante de tamaño distinto
  (la fuente dominante de *band-gap bowing* en aleaciones semiconductoras
  reales)— está estructuralmente ausente de la etiqueta con la que se
  reentrena el surrogate. El modelo puede aprender la tendencia composicional
  gruesa; no puede aprender curvatura de mezcla que dependa de relajación
  local, porque esa relajación nunca ocurre en los datos que ve.

- **`smearing = 0.01 eV` FermiDirac, con excepción a `0.2 eV` para Sn.** El
  ensanchamiento térmico de las ocupaciones ayuda a converger el SCF cuando
  hay estados casi degenerados cerca del nivel de Fermi. Que Sn necesite un
  ensanchamiento veinte veces mayor no es un ajuste arbitrario de
  conveniencia numérica: el Sn²⁺ tiene un par solitario 6s² estereoquímicamente
  activo y una conocida tendencia a oxidarse hacia Sn⁴⁺ (autodopaje), y las
  perovskitas de Sn son experimentalmente más propensas a comportamiento
  casi metálico que sus análogas de Pb. El ensanchamiento grande es la firma
  numérica de una tendencia física real del elemento — con el costo de que,
  en un material con bandgap ya pequeño, un `smearing` grande puede poblar
  artificialmente estados cerca del borde y distorsionar el propio `Eg` que
  se está intentando medir.

## 6. Caracterización profunda: cuando sí importa el número exacto

Los pocos candidatos que sobreviven el cribado reciben el tratamiento caro,
sobre el material de validación α-CsPbI₃ (5 átomos, `Pm̄3m`, `a₀≈6.18 Å`) y
sus fases γ (`Pnma`, tilt de Glazer a⁻b⁺a⁻, metaestable a 25 °C) y δ (`Pnma`,
octaedros por **arista** compartida en vez de vértice — sin efecto
perovskita electrónico alguno, aunque la fórmula química sea la misma).

| Paso | Qué mide físicamente |
|---|---|
| `relax` (PBEsol+D3) | Geometría de mínima energía real. PBEsol corrige el sobre-suavizado de PBE en sólidos densamente empaquetados; D3 añade la dispersión de van der Waals de largo alcance que ninguna GGA captura, relevante incluso sin catión orgánico. |
| `scf` → `bands` → `dos` | Densidad autoconsistente, dispersión de bandas (gap directo/indirecto, dónde cae el extremo) y carácter orbital por energía — qué orbitales atómicos forman cada banda. |
| `soc`, `soc_pbe` | Acoplamiento espín-órbita perturbativo: efecto relativista que escala fuertemente con número atómico. Divide y hunde el mínimo de la banda de conducción (carácter p de Pb/Bi) — por eso PBE+SOC da 0.60 eV frente a 1.44 eV sin SOC en CsPbI₃: casi la mitad del gap desaparece por relatividad, no por química. |
| `scan`, `r2scan` (+ variantes SOC) | Meta-GGA: añade dependencia de la densidad de energía cinética, describe mejor el hueco de intercambio-correlación que una GGA pura sin llegar al costo de un híbrido. |
| `hse06` (+ variantes) | Funcional híbrido: mezcla una fracción de intercambio exacto de Hartree-Fock, que cancela directamente buena parte del error de autointeracción de PBE. Es la estimación de gap más fiable disponible aquí fuera de GW. |
| **Scissor** (`bandgap_correction.py`) | `Eg = E_PBE+D3 + χ_SOC + χ_HSE`, con `χ_SOC = Eg(PBE+SOC) − Eg(PBE) ≈ −0.79 eV` y `χ_HSE = Eg(HSE06) − Eg(PBE) ≈ +0.32 eV` calculados en celdas pequeñas y trasladados. Asume que los dos efectos —relativista y de intercambio exacto— son aproximadamente aditivos e independientes de la celda; da ≈ 1.52 eV frente a 1.73 eV experimental (Sutton et al., *ACS Energy Lett.* 2018) a ~5× el costo de PBE en vez de ~60×. |
| `hessian`, `phonons` | Matriz dinámica: frecuencias reales y positivas confirman un mínimo local verdadero; una frecuencia imaginaria (modo blando) señala una distorsión de menor simetría hacia la que el material realmente quiere caer — el mecanismo físico exacto detrás de la competencia α/γ/δ. |
| `pes` | Barrido de energía a lo largo de un modo blando: si aparece un doble pozo, cuantifica la barrera entre polimorfos — de nuevo, la física de la transición de fase. |
| `loto` | Separación LO-TO: el campo eléctrico macroscópico que un fonón óptico longitudinal de longitud de onda larga genera en un cristal iónico/polar. Diagnóstico directo de cuán polar es el enlace — relevante para el apantallamiento dieléctrico y la física de polarones grandes que se invoca para explicar la tolerancia a defectos de estas perovskitas. |
| `formation_energy` | Entalpía de formación **contra las fases binarias competidoras reales** (p. ej. CsI + PbI₂), no contra los elementos — más riguroso que el `Eform` barato del MLFF de cribado (sección 4), que compara contra elementos y no contra el competidor de verdad. |
| `effective_masses` | Curvatura de banda en el extremo — masa efectiva pequeña (banda dispersiva) es la firma de los estados antienlazantes s-p que hacen buen transporte en estas perovskitas. |
| `optical` → `sq_limit` | Función dieléctrica/absorción desde la estructura electrónica, y de ahí el límite Shockley-Queisser real (sección 1) para *este* material, no el genérico. |
| `oghma_device` | Simulación de dispositivo (drift-diffusion + óptica): del límite intrínseco del material a la eficiencia realista con recombinación de interfaz, contactos y transporte — el paso de "podría" a "en un dispositivo real daría". |

## 7. Auditoría: dónde la aproximación deja de tener sentido físico

Cuatro hallazgos, de mayor a menor impacto sobre las conclusiones del
pipeline. Ninguno es un error de programación — son lugares donde una
simplificación razonable en aislamiento deja de serlo al conectarse con el
resto del sistema.

### 7.1 La ventana fotovoltaica compara un PBE crudo contra un límite experimental — **crítico**

La sección 1 deriva `[1.1, 1.8]` eV del límite Shockley-Queisser, que se
calcula sobre el bandgap **real** (el que absorbe/emite fotones de verdad).
La sección 5 establece que el surrogate se reentrena contra `Eg` de PBE de un
solo punto, sin SOC, sobre geometría idealizada — un número que la propia
sección 6 documenta que se desvía del experimental en varias décimas de eV,
en una dirección que además depende del elemento B (la cancelación
PBE-sin-SOC/HSE06+SOC de la sección 6 es casi una coincidencia calibrada para
Pb; no hay razón para que valga igual para Sn, Ge, Bi o In, cuyo acoplamiento
espín-órbita es mucho menor por tener número atómico mucho más bajo).

Es comparar una regla calibrada en un sistema de unidades contra un umbral
definido en otro. Mientras el surrogate usaba el modelo de fábrica (congelado,
nunca reentrenado — ver el registro de cambios de la rama), esta
inconsistencia no se manifestaba. En cuanto el ciclo de aprendizaje se cerró
de verdad, el surrogate aprendió que esta familia Sn–I tiene `Eg_PBE ≈ 1.0`
eV, la ventana lo descartó en bloque, y el protocolo se declaró terminado
tras una sola ronda con miles de candidatos sin verificar. Documentado en
detalle, con datos, en
[issue #7](https://github.com/RxWhizz/PEROVOWL/issues/7). No es un fallo de
código: es una decisión de calibración pendiente — aplicar un scissor
(sección 6) antes de comparar contra la ventana, o entrenar el surrogate
contra un `Eg` ya corregido usando `band_gap_gga_eV` como insumo en vez de
objetivo directo.

### 7.2 El filtro geométrico no compite contra el politipo real — **importante**

El factor de tolerancia y el octaédrico son condiciones necesarias, no
suficientes (sección 2). CsPbI₃ es el ejemplo servido en bandeja por este
mismo repositorio: con los radios de este código, `t(CsPbI₃) = 0.807` y
`μ(CsPbI₃) = 0.541` — dentro de las dos ventanas aceptadas, sin margen — y
sin embargo CsPbI₃ es *precisamente* el material cuya fase estable a 25 °C es
la δ (amarilla, sin conectividad de esquinas, `Eg_exp ≈ 2.82 eV`, inútil como
fotovoltaico), no la α cúbica que el resto del pipeline construye y evalúa
(sección 5, sección 6). El cribado geométrico + el `Eform` barato del MLFF
(que compara contra elementos, no contra el competidor no-perovskita — sección
4) no tienen ningún mecanismo para atrapar esto: solo el cálculo de fonones
de la caracterización profunda (sección 6) lo haría, y ese paso nunca se
ejecuta sobre el grueso del espacio de búsqueda por costo. Cualquier
candidato con `t` cerca del extremo inferior de la ventana debería tratarse
como "geométricamente plausible", no como "confirmado cúbico a temperatura
ambiente".

### 7.3 El radio del sitio A puede estar usando la coordinación equivocada — **verificar**

`src/ml_surrogate/features.py` documenta `r_A` como radio de Shannon a
coordinación 12 — la coordinación real del sitio A en una perovskita ABX₃,
rodeado por 12 aniones X en los vértices del cuboctaedro que forman los
octaedros vecinos. Pero los valores usados (Cs 1.67, Rb 1.52, K 1.38 Å)
coinciden exactamente con los que **el propio**
`src/dft_cspbi3/analysis/structural.py`, en la misma base de código, etiqueta
como coordinación **6** (`CN6`) para esos mismos iones, listando además unos
valores de `CN12` distintos (Cs 1.74, Rb 1.61, K 1.64 Å) que no se usan en
ninguna parte del cribado. El radio a 12 coordinaciones es mayor que a 6 (a
más vecinos, la nube electrónica del ion se estira más) — usar el número más
pequeño **subestima** `r_A` de forma sistemática para cada candidato del
espacio de búsqueda, lo que desplaza hacia abajo el factor de tolerancia de
todos ellos por igual. El efecto neto es una traslación sistemática del
umbral de aceptación, no un ruido aleatorio: candidatos genuinamente
próximos a `t_min = 0.80` con la coordinación correcta podrían estar
entrando o saliendo del cribado por este desajuste. Ameritа una
verificación directa contra Shannon (1976) *Acta Cryst.* A32:751 antes de
recalibrar cualquier umbral.

### 7.4 La mezcla composicional es lineal; el bandgap real no siempre lo es — **menor, ya mitigado en parte**

Los radios, electronegatividades y cargas efectivos de un sitio mixto se
calculan como promedio lineal ponderado por fracción (tipo Vegard). Es la
aproximación estándar de primer orden y una entrada razonable para que un
modelo de árboles aprenda no-linealidad a partir de datos reales. El punto
débil no está en usarla como *descriptor de entrada* — está en que, como
establece la sección 5, la estructura DFT que produce la *etiqueta* de
entrenamiento nunca relaja localmente alrededor de un átomo de tamaño
distinto al del resto del sitio, que es el origen microscópico dominante de
la curvatura de mezcla (*band-gap bowing*) en aleaciones semiconductoras
reales. El surrogate puede aprender la tendencia composicional gruesa; no
puede aprender la curvatura fina porque el proceso físico que la produce no
está en ninguna parte de los datos con los que se entrena.

## 8. Referencias

- GPAW: J. J. Mortensen et al., *J. Chem. Phys.* **160**, 092503 (2024)
- ASE: A. H. Larsen et al., *J. Phys.: Condens. Matter* **29**, 273002 (2017)
- PBEsol: J. P. Perdew et al., *Phys. Rev. Lett.* **100**, 136406 (2008)
- HSE06: J. Heyd, G. E. Scuseria, M. Ernzerhof, *J. Chem. Phys.* **118**, 8207 (2003)
- DFT-D3: S. Grimme et al., *J. Chem. Phys.* **132**, 154104 (2010)
- Radios iónicos de Shannon: R. D. Shannon, *Acta Cryst.* A32, 751 (1976)
- Radios efectivos de MA/FA: G. Kieslich, S. Sun, A. K. Cheetham, *Chem. Sci.* 5, 4712 (2014)
- Factor de tolerancia: V. M. Goldschmidt, *Naturwissenschaften* 14, 477 (1926)
- Bandgap experimental α-CsPbI₃: G. Sutton et al., *ACS Energy Lett.* 2018
- Bandgap experimental γ-CsPbI₃: J. Steele et al., *JACS* 2019
- Espectro solar de referencia: ASTM G173-03 (AM1.5G)
