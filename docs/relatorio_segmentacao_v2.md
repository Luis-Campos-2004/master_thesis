# Relatório completo — segmentação de formas na pele tátil com riscas (FTP)

Luís Campos · branch `luis/baseline-validation` · versão 2, 15 de outubro de 2026
(substitui a versão de 8 de outubro, `docs/relatorio_segmentacao.md`, que fica guardada)

Este documento regista **tudo o que foi feito**, por ordem, com todos os números. Serve de base para escrever o relatório da tese. Os valores são percentagens, salvo indicação em contrário.

---

## 0. Resumo em 10 linhas

1. O código original do Liam não tinha nenhuma medição da qualidade da segmentação. Criei uma ferramenta que compara cada máscara com um contorno desenhado à mão (Dice, IoU, precisão do contorno a 1 mm, distâncias em mm).
2. **Fotos antigas** (5 fotos, câmara e contornos do Liam): o meu modo de contacto passa o Dice de 80.9% para **82.9%**, o IoU de 68.0% para **71.0%** e o contorno a 1 mm de 51.4% para **67.2%**, face ao melhor modo do Liam (tight).
3. Estes números foram afinados nas mesmas 5 fotos. Em formas não vistas (validação *leave-one-shape-out*), o contorno a 1 mm fica em ~60%.
4. **Fotos novas** (48 fotos, 8 formas × 6 ângulos, câmara nova, contornos desenhados por mim): o meu método com corte a 15% dá **66.7%** de Dice contra **54.4%** do tight do Liam (+12.3 pontos, melhor em 40/48 fotos, p = 2×10⁻⁷).
5. **Combinar os 6 ângulos** dá **69.0%** de Dice (+2.4 pontos face a uma foto sozinha, não significativo, p = 0.13). Ajuda nas formas de uma só peça e piora nas formas com peças separadas.
6. **O ajuste de brilho/contraste** sugerido pelo supervisor melhora a aparência das fotos, mas **não muda a segmentação** (37/47 fotos com o número certo de contactos, com e sem ajuste).
7. **Melhorar o setup** (enquadramento, exposição, luz) também não mudou o resultado. O contraste das riscas continua em metade do do Liam (0.28 contra 0.54) e o tipo de sinal mantém-se.
8. **A diferença principal entre setups é física:** no do Liam, a zona pressionada aparece como um planalto uniforme na fase; no meu, como uma rampa, com uma variação de período uniforme no interior da forma. Isto depende da geometria da câmara, não da qualidade da foto.
9. No mapa de **variação do período das riscas**, as formas aparecem inteiras e nítidas nas minhas fotos. É o sinal certo para o meu setup, mas um primeiro teste simples ainda não supera o método atual (59.6% contra 64.8% de Dice em 6 fotos).
10. Pendentes: aplicar uma pequena correção no `refine_contour`, guardar tudo no git e confirmar com o supervisor se a meta de 80% é em Dice ou em IoU.

---

## 1. Contexto e ponto de partida

### 1.1 Objetivo
O supervisor pediu para melhorar a **segmentação das formas pressionadas na membrana** (o contorno de cada forma), com uma meta de cerca de 80%. Ainda falta confirmar se a meta se refere ao Dice ou ao IoU.

### 1.2 O código do Liam
- Repositório do Liam Gibbons; o último commit dele é o `5f63d96` (17 de agosto de 2026). O original de `detect_shape.py` está guardado como `src/tactile/detect_shape_liam_original.py`.
- A segmentação está em `src/tactile/detect_shape.py`, função `detect()`:
  1. recorte quadrado central (`CROP_RATIO = 0.31` do lado menor) e redimensionamento para 768×768 px (`PROC_SIZE`);
  2. demodulação FTP: encontra a portadora (o pico das riscas no espetro) e aplica um filtro passa-banda gaussiano com largura `BW_FRAC = 0.55` da frequência da portadora;
  3. diferença de fase entre a foto pressionada e a referência, desenrolada (`unwrap_phase`);
  4. filtro passa-alto (σ = 0.117 × 768 ≈ 90 px) e suavização (`SMOOTH_SIGMA_FRAC = 0.008`, ≈ 6 px);
  5. *z-score* robusto, limiar com histerese, morfologia, filtro de componentes e tratamento de buracos;
  6. dois modos:
     - **default (footprint)**: toda a zona deformada, incluindo o halo. É usado pelo pipeline de força (`uniform_reconstruct.py`, com `CALIB_FOOTPRINT_SCALE = 1.874` calibrado sobre esta máscara);
     - **tight**: corta cada contacto a 35% do seu próprio pico (`TIGHT_LO_FRAC = 0.35`).
- Canais opcionais: `--use-orient` (orientação das riscas) e `--use-amp` (queda da amplitude das riscas).
- **Não existia nenhuma medição da qualidade da segmentação.** O `verification/audit_shape.py` mede a qualidade das fotos, não o algoritmo; a sua função `gt_area_fraction` usa Otsu em cinzento e não lê os contornos vermelhos.

### 1.3 Fotos antigas e contornos de referência (Liam)
- `data/raw/shape_pictures/<Forma>/`: `img_01.jpg` é a referência (membrana em repouso), `img_02.jpg` a foto pressionada e `*_gt.jpg` o contorno desenhado à mão a vermelho.
- Fotos de 4608×3456 px.
- Há contornos para **F, Ring, Square, Star e Three Circles**. O P e o Square Circle não têm contorno; o F tem uma segunda foto (`img_03`) sem contorno exato.
- **Verifiquei que cada contorno foi desenhado sobre o `img_02` da mesma pasta**: os píxeis fora do vermelho são idênticos (diferença média 0.00). O contorno do Square tem 1 px a menos de largura (4607 px), o que é irrelevante.
- O traço vermelho tem 58–73 px na foto original (≈ 2 mm), ou seja ~24 px na imagem de trabalho de 768 px.
- **Escala**: 32.9 px/mm na foto original e **11.8 px/mm** na imagem de 768 px, medida pelo círculo de calibração de 20 mm (314 mm²; 43 713 px na imagem de 768).
- **Período real das riscas**: ~75–77 px na foto original (≈ 2.3 mm), ou 27.1 px na imagem de 768. Ângulo da portadora: −148°.

---

## 2. Ferramenta de avaliação e métricas

Script: `verification/eval_segmentation.py`.

**Leitura do contorno de referência (GT):**
1. vermelho = `R − max(G, B) > 70`, seguido de um fecho morfológico 9×9;
2. cada região fechada conta como objeto se estiver dentro de um número **ímpar** de contornos. Assim o buraco do Ring fica vazio;
3. os píxeis do traço são divididos pelo meio, o que põe a fronteira no centro da linha desenhada;
4. o contorno sofre o mesmo recorte e redimensionamento (768 px) que a foto.

**Métricas**, comparando a máscara detetada (P) com o GT (G):
- **Dice** = 2|P∩G| / (|P| + |G|);
- **IoU** = |P∩G| / |P∪G|. Mede o mesmo que o Dice numa escala mais exigente: Dice 80% = IoU 66.7%;
- **precisão e recall** da área;
- **contorno a X mm (F@Xmm)**: média harmónica entre a fração da borda detetada a menos de X mm da borda verdadeira e a fração da borda verdadeira a menos de X mm da detetada. Calculei para 0.5, 1 e 2 mm;
- **ASSD**: distância média entre as duas bordas, em mm;
- **HD95**: distância a 95% entre as bordas, em mm;
- **número de contactos** (peças separadas).

**Estatística:** teste de Wilcoxon emparelhado, comparando os dois métodos na mesma foto.

**Validação *leave-one-shape-out* (LOSO):** escolher os parâmetros com 4 formas e testar na 5.ª, repetindo para cada forma.

---

## 3. Fase A — Diagnóstico do método do Liam (fotos antigas)

### 3.1 Resultados de partida
| modo | IoU | Dice | contorno 1 mm | contorno 0.5 mm | ASSD |
|---|---|---|---|---|---|
| default (footprint) | 58.0 | 72.5 | 21.2 | 7.0 | 2.38 mm |
| tight | 68.0 | 80.9 | 51.4 | 24.5 | 1.27 mm |

IoU por forma:

| forma | default | tight |
|---|---|---|
| F | 52.7 | 61.9 |
| Ring | 70.3 | 69.7 |
| Square | 69.9 | 73.9 |
| Star | 61.5 | 70.7 |
| Three Circles | 35.3 | 63.7 |

- **Default:** recall ~100% mas precisão de só 35–72%, porque inclui o halo à volta do objeto. Serve o pipeline de força, não a forma.
- **Tight:** HD95 ≈ 44 px (≈ 3.7 mm).

### 3.2 O que o diagnóstico mostrou
- **A fase é uma "lomba" positiva sobre o contacto:** 93–100% dos píxeis do GT têm z > +2. A borda do GT fica a 72–92% da altura do planalto.
- O "modo dipolo" do código nunca é ativado (`w_opp = 0` nas 5 fotos), por isso o canal de *strain* nunca é usado. Usar o gradiente da fase como sinal dá IoU de 5–30%, porque só marca bordas.
- **Os canais opcionais pioram:** tight + orientação dá IoU 61.7%, tight + amplitude 48.8% e os dois juntos 45.5%. Contorno a 1 mm: 34.7 / 32.1 / 23.0, contra 52.1 do tight.
- **Teto de anotação** (comparar o GT com ele próprio deslocado): ±0.3 mm dá IoU 87–95%; ±0.7 mm dá 75–91%; **±1 mm dá 64–87%, média ~76%**. Com um traço de 2 mm, nem um método perfeito chegaria aos 100%.
- **Desvio sistemático:** o melhor deslocamento rígido da máscara tight sobre o GT é, em média, (−7.8, −8.2) px (≈ 1 mm), quase todo **na direção perpendicular às riscas**. Corrigir com o desvio médio aprendido nas outras formas (LOSO) dá IoU 68.0 → 69.9 e contorno 51.4 → 58.0.
- **Precisão do contorno por orientação da borda** (tight): borda perpendicular às riscas 63.2%, oblíqua 53.7%, paralela 38.9%.
- **Fotos de força** (`data/raw/force_pictures/`): a variação de fase é ≤ 0.2 rad, contra 3–10 rad nas fotos de formas. O IoU contra a máscara do círculo de calibração é de 3–23%. Não servem para afinar a segmentação.

---

## 4. Fase B — Modo de contacto v2 (alterações a `detect_shape.py`)

### 4.1 Os três passos
Aplicados por cima do corte tight, só quando pedidos (`detect(..., **CONTACT_PARAMS)` ou `--contact`):
1. **Sinal mais nítido**: suavização da fase de 0.008 para **0.004** da imagem.
2. **Encaixe da borda** (`refine_contour`): um contorno ativo geodésico move cada borda para onde a fase varia mais depressa, só numa faixa de um período das riscas (~27 px) à volta da borda. Usa σ = 0.0026 × 768 (≈ 2 px) e 20 iterações. Depois limpa manchas e buracos minúsculos (< 0.04% da imagem) e suaviza o contorno (σ ≈ 6 px).
3. **Compensação do deslocamento** (`compensate_displacement`): calcula o deslocamento das riscas, `u = −Δφ·n/(2π|f|)`, com o fundo medido a 40 px da máscara e suavização de ~4 px, e puxa a máscara de volta **25%** desse deslocamento (`disp_alpha = 0.25`).

Parâmetros: `CONTACT_PARAMS = dict(tight=True, smooth_frac=0.004, refine=True, disp_alpha=0.25)`.

Linha de comandos nova: `--contact`, `--reference`, `--deformed` e `--stem`. O nome dos ficheiros de saída passou a sair da pasta e do ficheiro (antes estava fixo em `"star"`).

### 4.2 Como cheguei a estes passos (fotos antigas, média das 5)
| variante | IoU (J) | contorno 1 mm (F) |
|---|---|---|
| tight (partida) | 68.0 | 51.4 |
| suavização 0.004 | 68.0 | 55.8 |
| largura de banda 0.8 | 68.7 | 53.5 |
| largura de banda 0.4 | 67.9 | 50.6 |
| `TIGHT_LO_FRAC` 0.30 | 68.9 | 43.8 |
| suavização final 0.004 | 67.9 | 51.6 |
| Chan-Vese | 71.0 | 44.2 |
| compensação, fase com passa-alto, α = 0.75 | 69.3 | 55.7 |
| compensação, fase sem filtro, α = 0.25 | 70.0 | 57.0 |
| suavização 0.004 + compensação α = 0.25 | 69.9 | 61.4 |
| + encaixe da borda (GAC σ = 2 px, 20 it.) | 70.7 | 67.1 |
| **+ suavização final do contorno (versão final)** | **71.0** | **67.2** |

As 8 configurações do encaixe da borda que testei dão todas entre 65.9% e 67.7% de contorno, o que mostra que o passo é estável.

### 4.3 Resultado final nas fotos antigas
| | Dice | IoU | contorno 1 mm | contorno 0.5 mm | contorno 2 mm | ASSD | HD95 |
|---|---|---|---|---|---|---|---|
| tight (Liam) | 80.9 ± 3.2 | 68.0 ± 4.5 | 51.4 ± 12.2 | 24.5 | 81.5 | 1.3 mm | 3.7 mm |
| **modo de contacto** | **82.9 ± 3.6** | **71.0 ± 5.2** | **67.2 ± 1.9** | **36.6** | **85.1** | **1.1 mm** | **3.4 mm** |

Por forma (Dice / IoU / contorno 1 mm):

| forma | tight | modo de contacto |
|---|---|---|
| F | 76.5 / 61.9 / 50.5 | 79.0 / 65.3 / 65.7 |
| Ring | 82.1 / 69.7 / 44.3 | 86.3 / 75.9 / 69.1 |
| Square | 85.0 / 73.9 / 33.5 | 87.5 / 77.8 / 64.9 |
| Star | 82.8 / 70.7 / 69.0 | 83.0 / 70.9 / 66.5 |
| Three Circles | 77.8 / 63.7 / 59.6 | 78.9 / 65.1 / 69.8 |

- **Teste de Wilcoxon (5 fotos):** o IoU melhora em 5/5 fotos (p = 0.0625, o mínimo possível com 5 pares); o contorno melhora em 4/5 (+15.8 pontos, p = 0.125).
- **Consistência:** a variação do contorno entre formas caiu de ±12.2 para ±1.9 pontos.
- **Por orientação da borda** (modo de contacto): perpendicular 77.7%, oblíqua 66.9%, paralela 64.9%, contra 63.2 / 53.7 / 38.9 do tight. Em fatias de 15° (0° = borda paralela às riscas): 63.4 / 68.6 / 68.7 / 65.3 / **81.0** / 76.4. A precisão só é alta a menos de 30° da perpendicular.
- **Regressão:** os modos default, tight e orientação+amplitude dão máscaras idênticas, píxel a píxel, às do código original (30 casos: 10 pares × 3 modos).
- **Pipeline de força:** no par de `final_images` dá 35.6 N e 2.72 mm de profundidade, sem alterações.

---

## 5. Fase C — Validação honesta e o que ficou de fora (fotos antigas)

### 5.1 Pesquisa de parâmetros *leave-one-shape-out*
192 combinações: largura de banda {0.55, 0.7} × suavização {0.003, 0.004, 0.006, 0.008} × corte {0.30, 0.35, 0.40} × encaixe {não, sim} × compensação {0, 0.25, 0.5, 0.75}. Escolhi em cada ronda a melhor combinação em contorno, com a condição de o IoU não descer.

| forma testada | IoU (tight → escolhido) | contorno 1 mm (tight → escolhido) |
|---|---|---|
| F | 61.9 → 61.8 | 50.5 → 66.8 |
| Ring | 69.6 → 73.5 | 44.3 → 67.3 |
| Square | 73.9 → 73.6 | 33.5 → 46.0 |
| Star | 70.7 → 61.2 | 69.0 → 68.0 |
| Three Circles | 63.7 → 52.5 | 59.6 → 51.3 |
| **média** | **68.0 → 64.5** | **51.4 → 59.9** |

- **O encaixe da borda e a compensação α = 0.25 foram escolhidos em todas as rondas.** Os outros três parâmetros mudaram de ronda para ronda, sinal de que afinar mais é ajustar-se a estas 5 imagens.
- A melhor combinação usando as 5 formas (suavização 0.006) dá IoU 71.9% e contorno 67.7%, mas só em amostra.
- Esta pesquisa foi feita antes de acrescentar a suavização final do contorno.

### 5.2 Classificador por píxel (Random Forest, LOSO)
18 variáveis por píxel: o score, o score relativo ao pico, o score suavizado (4, 8 e 16 px), o gradiente, a altura de fase, o score a ±0.5 e ±1 período ao longo da portadora e das riscas, e a distância às bordas do modo de contacto e do tight. 200 árvores, profundidade 14.

| forma testada | modo de contacto: Dice / IoU / contorno | Random Forest |
|---|---|---|
| F | 79.0 / 65.3 / 65.7 | 85.9 / 75.2 / 69.5 |
| Ring | 86.3 / 75.9 / 69.1 | 78.3 / 64.3 / 63.2 |
| Square | 87.5 / 77.8 / 64.9 | 89.1 / 80.3 / 51.8 |
| Star | 83.0 / 70.9 / 66.5 | 83.9 / 72.3 / 55.1 |
| Three Circles | 78.9 / 65.1 / 69.8 | 75.5 / 60.6 / 69.1 |
| **média** | **82.9 / 71.0 / 67.2** | 82.5 / 70.6 / 61.7 |

- Em média não compensa. Com 4 formas de treino não generaliza.
- As variáveis mais importantes foram o score meio período ao lado ao longo da portadora (0.18) e a distância à borda do modo de contacto (0.17). A primeira confirma, por outro caminho, o efeito do deslocamento das riscas.
- Exigiu instalar o `scikit-learn 1.9.1` no `.venv`, que não está no `requirements.txt`.

### 5.3 Outras tentativas
| tentativa | resultado (média das 5) |
|---|---|
| Fundo polinomial (graus 1–3) | IoU 22–38%, falha |
| Fundo com o contacto excluído | melhor IoU 67.4% (LOSO 64.8%) |
| Nível de declive máximo | 30–43% |
| Cortes fixos de 45% / 55% / 65% | IoU 54.1 / 38.9 / 26.1 |
| Filtro *notch* da ondulação das riscas | IoU 71.3, contorno 66.2, contorno 0.5 mm 38.2 |
| *Notch* + 40 iterações do encaixe | 71.6 / 68.1 / 39.9 |
| Média num período ao longo da portadora | 71.5 / 63.4 |
| Suavizar a máscara (σ 3 / 6 px) | 70.8 / 67.4 e 71.0 / 67.3 |
| Tirar o fundo da imagem antes da FTP | IoU 71.1, contorno 68.7 (+1.6, fica como opção) |

### 5.4 Problemas encontrados no modo de contacto
- **P das fotos antigas:** o modo de contacto deixa uma mancha solta de ~170 px e conta 2 contactos. A causa é a ordem dentro do `refine_contour`, que limpa as manchas **antes** de suavizar. A correção (suavizar primeiro) foi testada: o P passa a 1 contacto e os números ficam iguais. **Ainda não está aplicada.**
- **A barriga do P desaparece** no tight e no modo de contacto, porque foi pressionada com menos força e fica abaixo do corte.
- **No Square Circle** (2 contactos certos), o círculo do modo de contacto fica menos redondo do que o do tight.

---

## 6. Fase D — Fotos novas com rotação (recolha de 5 de outubro)

### 6.1 Recolha
- 8 formas (F, P, M, Ring, Square, Square Circle, Star, Three Circles) × 6 ângulos (0°, 60°, …, 300°) = 48 fotos, mais uma referência.
- Referência às 14:09:13. Fotos das 14:09:32 às 14:38:50: F 14:09–14:11, P 14:12–14:14, Ring 14:14–14:16, Square 14:19–14:20, Square Circle 14:21–14:23, Three Circles 14:27–14:28, Star 14:34–14:36, M 14:37–14:38.
- Câmara diferente da do Liam: **2520×1680 px**, ~450 KB por foto, período das riscas ~51 px, ângulo da portadora −150°, **22 px/mm**.
- **Janela de análise ajustada** para manter 1 mm = 11.8 px na imagem de 768: `crop_ratio` = 0.432, calculado a partir do período.
- **A câmara mexeu-se** até ~16 px em relação à referência (por exemplo o M a ~(+15, −6) px). Cada foto é alinhada com a referência antes da análise.
- Os Three Circles a 240° e 300° eram o mesmo ficheiro. Foi corrigido no conjunto v3 (secção 7).
- Pasta: `data/raw/shape_pictures_v2/<Forma>/rot_XXX.jpg` e `reference.jpg`.

### 6.2 Diferença física no sinal
- **O sinal está invertido** (negativo) e **não é uniforme**: a deformação é mais forte de um lado do contacto, sempre na mesma direção.
- Razão entre o pico negativo e o positivo: Three Circles 3.41, F a 300° 3.80, Square a 60° 2.40. Nas fotos antigas era 0.13.
- **Força do sinal** (pico do z-score): 13.2 / 17.4 / 10.7, contra 24.7 nos Three Circles antigos. Cerca de metade.
- O corte do modo de contacto (35% do pico) só guarda o lado forte, o que dá meias-luas e formas partidas.

### 6.3 Ajuste de brilho/contraste (`src/tactile/adjust_photos.py`, sugestão do supervisor)
Três passos:
1. alinhamento com a referência, por correlação de fase nas faixas laterais do suporte;
2. correção da iluminação, dividindo por uma versão muito desfocada (σ = 150 px);
3. esticamento do contraste entre os percentis 1 e 99 dentro da membrana. Há também uma opção CLAHE.

Comparação sem GT, com os critérios número certo de contactos e variação da área entre ângulos:

| versão das fotos · método | contactos certos | variação da área (CV) |
|---|---|---|
| original · modo de contacto | 19/47 (40%) | 33.1% |
| original · corte 15% | 35/47 (74%) | 25.1% |
| original · modo de contacto + amplitude | 22/47 | 40.3% |
| original · corte 15% + amplitude | 36/47 (77%) | 21.4% |
| ajustada · modo de contacto | 23/47 (49%) | 34.4% |
| ajustada · corte 15% | 37/47 (79%) | 25.8% |
| ajustada · modo de contacto + amplitude | 17/47 | 44.2% |
| ajustada · corte 15% + amplitude | 35/47 | 22.7% |

- Com a configuração final (janela automática 0.432, corte 15%): **37/47 com e sem ajuste**. Uma foto melhora (F a 300°, de 2 para 1 contacto) e outra piora (Square a 0°, de 1 para 2).
- **Conclusão:** o ajuste deixa as formas visíveis a olho, mas não muda a segmentação. O método mede a posição das riscas, que não depende do brilho nem do contraste.
- **Comparar com o pico da vizinhança** em vez do pico do contacto piora: 26/47 (1 cm, 35%), 8/47 (1 cm, 50%), 10/47 (2 cm, 35%).
- **Por forma** (ajustada, corte 15%, contactos certos / área média / CV): F 5/6, 525 mm², 37% · M 4/6, 665, 17% · P 4/6, 524, 42% · Ring 6/6, 615, 17% · Square 5/6, 455, 21% · Square Circle 5/6, 704, 5% · Star 3/6, 564, 32% · Three Circles 5/5, 344, 35%.

---

## 7. Fase E — Contornos nas fotos novas e avaliação completa (conjunto v3)

### 7.1 Os meus contornos
- Desenhei os 48 contornos entre 6 de outubro (23:48) e 7 de outubro (09:32), com linhas vermelhas finas (1–2 px), gravadas como `*_gt.jpg`.
- Com a compressão JPG, a linha mistura-se com as riscas (cor B,G,R ≈ 96,100,157). Por isso **a linha é detetada como a diferença face à foto limpa**.
- O contorno do F a 0° tinha uma pequena abertura. É fechada automaticamente, ligando pontas a menos de 90 px (~4 mm).

### 7.2 Montagem do conjunto v3 (`verification/build_dataset_v3.py`)
- Cada desenho é associado à foto sobre a qual foi feito, comparando píxeis.
- **Three Circles:** os ângulos seguem os nomes dos desenhos. A foto que estava como 0° é a de 60°, a de 60° a de 120°, e assim por diante até 300°.
- **A foto nova dos Three Circles a 0°** só existia com o desenho por cima. A versão limpa foi reconstruída preenchendo a linha a partir dos vizinhos (*inpainting*).
- Pastas: fotos em `data/raw/shape_pictures_v3/`, contornos em `data/annotations/shape_pictures_v3/`.
- **Áreas dos contornos**, coerentes entre ângulos: F 375–411 mm² · M 489–552 · P 409–458 (buraco 64–72) · Ring 529–592 (buraco 369–381) · Square 478–539 · Square Circle 566–577 (2 peças) · Star 160–212 · Three Circles 232–239 (3 peças).

### 7.3 Resultados nas 48 fotos (`verification/eval_photos_v3.py`)
Todos os métodos correm sobre as mesmas fotos ajustadas e com a mesma janela.

| método | Dice | IoU | contorno 1 mm | contorno 2 mm | ASSD |
|---|---|---|---|---|---|
| default do Liam | 61.9 ± 15.2 | 46.6 ± 15.9 | 23.0 ± 16.5 | 45.9 | 2.9 mm |
| tight do Liam | 54.4 ± 17.7 | 39.5 ± 17.5 | 36.8 ± 17.0 | 63.2 | 2.8 mm |
| modo de contacto (35%) | 54.4 ± 19.2 | 39.7 ± 18.5 | **44.4** ± 17.7 | **66.7** | 2.9 mm |
| modo de contacto, corte 15% | 66.7 ± 13.9 | 51.6 ± 15.6 | 38.2 ± 20.6 | 62.6 | **2.2 mm** |
| corte 15% + 6 ângulos combinados | **69.0** ± 13.0 | **54.1** ± 14.1 | 33.8 ± 12.1 | 57.9 | **2.2 mm** |

**Testes de Wilcoxon emparelhados (48 fotos):**

| comparação | Dice | IoU | contorno 1 mm |
|---|---|---|---|
| corte 15% vs tight | +12.3, melhor em 40/48, p = 2.2×10⁻⁷ | +12.1, p = 5.4×10⁻⁸ | +1.4, 28/48, p = 0.47 |
| combinado vs corte 15% | +2.4, 27/48, p = 0.13 | +2.5, p = 0.16 | −4.5, 21/48, p = 0.18 |
| combinado vs tight | +14.7, 32/48, p = 4.2×10⁻⁵ | +14.6, p = 3.2×10⁻⁵ | −3.1, 20/48, p = 0.31 |
| corte 35% vs tight | p = 0.1 | p = 0.1 | +7.6, p = 6×10⁻¹⁰ |
| default vs tight | p = 0.001 | p = 0.0007 | p = 2×10⁻⁹ |

**Dice por forma:**

| forma | default | tight | contacto 35% | corte 15% | combinado |
|---|---|---|---|---|---|
| F | 61.9 | 47.9 | 47.4 | 62.5 | **70.7** |
| M | 71.0 | 63.3 | 64.7 | 75.1 | **75.8** |
| P | 61.3 | 43.6 | 46.0 | 65.8 | **75.2** |
| Ring | 70.1 | 56.5 | 59.5 | 72.3 | **76.9** |
| Square | 64.4 | 41.9 | 43.7 | 67.5 | **74.9** |
| Square Circle | 83.8 | 81.9 | 82.0 | **86.5** | 80.9 |
| Star | 35.6 | 52.3 | **55.0** | 45.1 | 46.3 |
| Three Circles | 47.5 | 47.7 | 36.7 | **58.6** | 51.6 |

- **A Star é má em todos os métodos:** as deteções são ~3× maiores do que o contorno (~190 mm²).
- **O corte a 15% nas fotos antigas** dá Dice 79.9 ± 9.5, IoU 67.4 ± 12.0 e contorno 55.8 ± 9.1, pior do que o corte a 35% (82.9 / 71.0 / 67.2). **O melhor corte depende da câmara.**

---

## 8. Fase F — Combinação dos 6 ângulos

- **Método** (`verification/fuse_angles.py`):
  1. segmentar cada ângulo;
  2. estimar o eixo de rotação pela média dos centros das 6 máscaras (com ângulos igualmente espaçados os desvios cancelam-se) e afiná-lo pela concordância entre máscaras. O sentido de rotação estimado foi −1 em todas as formas;
  3. rodar cada máscara de volta a 0° e ficar com os píxeis vistos por **pelo menos 3 dos 6 ângulos**;
  4. para comparar com o contorno de cada foto, rodar a forma combinada para o ângulo dessa foto.
- **Concordância entre as máscaras rodadas** (IoU médio entre pares): 0.31–0.59.
- **Primeira estimativa, com os contornos do Liam como molde** (permite rodar, mover, espelhar e ±10% de tamanho):

| forma | um ângulo (média) | k=1 | k=2 | k=3 | k=4 | k=5 | k=6 |
|---|---|---|---|---|---|---|---|
| F | 55.4 | 53.2 | 63.3 | 60.4 | 59.7 | 45.7 | 12.8 |
| Ring | 55.9 | 56.1 | 65.8 | 65.9 | 55.7 | 19.8 | 1.2 |
| Square | 62.5 | 65.1 | 77.2 | 75.7 | 59.6 | 42.8 | 9.6 |
| Star | 60.3 | 41.3 | 63.9 | 73.7 | 78.3 | 67.8 | 23.9 |
| Three Circles | 35.1 | 34.4 | 51.0 | 53.5 | 15.1 | 0.2 | — |
| **média** | **53.8** | 50.0 | 64.2 | **65.8** | 53.7 | 35.3 | 11.9 |

  O melhor ângulo isolado dá 69.0% em média. Esta estimativa dava **+12 pontos**, mas ignora erros de posição.
- **Avaliação com os meus contornos (o número válido):** **+2.4 pontos de Dice** (69.0 contra 66.7%), não significativo (p = 0.13). Ajuda no F, P, Square, Ring e M; piora no Square Circle e nos Three Circles; o contorno a 1 mm piora 4.5 pontos.
- **Porque é que ajuda:** cada foto perde sempre o mesmo lado da imagem. Como a ponta roda, esse lado corresponde a partes diferentes do objeto, e combinar preenche o que cada foto perdeu e remove manchas que só uma foto vê.
- **Porque é que piora nas formas com peças separadas:** um pequeno erro no centro de rotação desloca cada peça.

### 8.1 Escolha do passo angular
Com os dados antigos, a precisão do contorno é alta a menos de 30° da perpendicular às riscas. **Passos de 60° garantem que cada borda cai nessa zona em exatamente um ângulo.** Passos de 30° dariam redundância, mas não melhorariam a melhor vista de cada borda.

---

## 9. Fase G — Setup melhorado (8 a 15 de outubro)

### 9.1 Qualidade da referência
Valores medidos dentro da membrana:

| | Liam | 5 out | setup melhorado |
|---|---|---|---|
| período das riscas | 76.9 px | 51.3 px | 41.2 px |
| diâmetro visível da membrana | 39 períodos | 37 | 39 |
| brilho médio (0–255) | 63 | 137 | 99 |
| píxeis saturados | 0% | 0% | 0% |
| **contraste das riscas** (centro / meio / borda) | **0.54 / 0.52 / 0.51** | 0.27 / 0.25 / 0.26 | 0.28 / 0.27 / 0.29 |
| luz do centro para a borda | +8% | +1% | +6% |

- **Melhorou** o enquadramento (membrana inteira e centrada), a exposição e a uniformidade da luz.
- **Não melhorou o contraste das riscas**, que continua em metade do do Liam. Possíveis causas: luz difusa a chegar à lente, foco ou compressão da câmara.

### 9.2 Toques com o setup melhorado (Square)
- **Toque 1** (referência `1.jpg` a 2520×1680 e foto `3.jpg` a 2176×1452, reduzida ao enviar):
  - pico do sinal 9.5 (sinal oposto 7.2), contra 8.6 no Square de 5 de outubro e 13.7 no do Liam;
  - corte 35%: 2 peças; corte 15%: 1 peça (~700 mm²).
- **Toque 2** (referência `4.jpg` e foto `5.jpg`, ambas a 2176×1452):
  - alinhamento exato (ECC): escala +0.23% e deslocamento (−0.9, −5.8) px;
  - as duas referências (`4.jpg` e `1.jpg`) coincidem a +0.01%.
- **Correção:** afirmei antes que o zoom mudava 3.4–3.5% entre a referência e a foto pressionada. **Não é verdade.** O alinhamento exato mostra uma diferença de 0.2%. O erro vinha da minha medição rápida do período, que é pouco precisa e é influenciada pelo contacto. As conclusões sobre o tipo de sinal mantêm-se.
- **Ajuste de brilho/contraste no toque 2:**

| | sem ajuste | com ajuste |
|---|---|---|
| contraste das riscas (só visual) | 0.048 | 0.093 |
| pico do sinal | 7.4 | 7.6 |
| peças, tight do Liam | 2 | 2 |
| peças, modo de contacto 35% | 2 | 3 |
| peças, corte 15% | 2 | 2 |
| área, corte 15% | 405 mm² | 438 mm² |

  O ajuste **não melhora** a segmentação.

### 9.3 Descoberta: a variação do período das riscas
- Calculei a **derivada da fase na direção perpendicular às riscas**, que é a variação local do período, a mesma grandeza que o pipeline de força do Liam usa.
- Nas minhas fotos (5 de outubro e setup melhorado), **a forma aparece inteira como um interior uniforme** (azul), com uma faixa forte (vermelha) num dos lados. F, P, anel, estrela, círculos e quadrado são todos reconhecíveis.
- Nas fotos do Liam, a mesma derivada dá só bordas: azul de um lado e vermelho do outro.
- **Força** (pico dominante / oposto): setup melhorado 11.1 / 5.2 (razão 0.47); 5 de outubro 30.0 / 15.1 (0.50); Liam 24.5 / 23.9 (0.98).
- **Interpretação:** no setup do Liam, a pressão desloca as riscas de forma uniforme (planalto na fase). No meu, muda o período dentro da zona pressionada, o que integrado dá uma rampa na fase. Isto depende da **geometria da câmara** (o ângulo e a distância a que vê a membrana), não da qualidade da foto.
- **Primeiras tentativas de segmentar com este sinal**, em 6 fotos com contorno (Square 0°, F 0°, Ring 0°, Three Circles 60°, Star 0°, P 0°):
  - preencher a "moldura" vermelha: 0%, porque a moldura não é fechada;
  - cortar o interior azul: melhor média **59.6%** de Dice (corte 0.2, σ 6 px), contra **64.8%** do corte a 15% nas mesmas fotos. Por foto: Square 63.5 (59.2), F 66.8 (69.9), Ring 62.3 (80.1), Three Circles 51.5 (52.7), Star 46.7 (52.2), P 66.6 (74.5). As máscaras ficam esburacadas por riscas finas na direção das riscas da membrana.
  - **Ainda não supera o método atual, mas é a pista principal** para o meu setup.
- Estas análises estão no scratchpad e ainda não estão no projeto.

---

## 10. Tabela final (para a tese)

Ficheiro: `results/segmentation_v2/method_comparison.png` (também `.csv` e `.md`).

| método | antigas: Dice | antigas: IoU | antigas: contorno 1 mm | novas: Dice | novas: IoU | novas: contorno 1 mm |
|---|---|---|---|---|---|---|
| Liam: default | 72.5 ± 11.3 | 58.0 ± 13.0 | 21.2 ± 10.1 | 61.9 ± 15.2 | 46.6 ± 15.9 | 23.0 ± 16.5 |
| Liam: tight | 80.9 ± 3.2 | 68.0 ± 4.5 | 51.4 ± 12.2 | 54.4 ± 17.7 | 39.5 ± 17.5 | 36.8 ± 17.0 |
| Modo de contacto (35%) | **82.9 ± 3.6** | **71.0 ± 5.2** | **67.2 ± 1.9** | 54.4 ± 19.2 | 39.7 ± 18.5 | **44.4 ± 17.7** |
| Modo de contacto, corte 15% | 79.9 ± 9.5 | 67.4 ± 12.0 | 55.8 ± 9.1 | 66.7 ± 13.9 | 51.6 ± 15.6 | 38.2 ± 20.6 |
| Corte 15% + 6 ângulos | — | — | — | **69.0 ± 13.0** | **54.1 ± 14.1** | 33.8 ± 12.1 |

- **Fotos antigas:** 5 fotos, contornos do Liam, parâmetros afinados nelas.
- **Fotos novas:** 48 fotos, os meus contornos; só o corte a 15% foi escolhido nelas, e sem os contornos.
- **Meta de 80%:** em Dice, as fotos antigas já a passam (82.9%). Em IoU, nenhum conjunto chega lá.

---

## 11. Limitações

1. **Contornos desenhados à mão:** o do Liam tem um traço de ~2 mm, e ±1 mm já dá ~76% de IoU. Os meus são mais finos, mas também são feitos a olho.
2. **Resolução na direção perpendicular às riscas:** limitada pelo período (~2.3 mm). As bordas paralelas às riscas são as piores.
3. **O melhor corte depende da câmara:** 35% na do Liam, 15% na minha. Ainda não é escolhido automaticamente.
4. **Tipo de sinal no meu setup:** rampa em vez de planalto, sinal ~metade do do Liam e contraste das riscas ~metade. Afeta todos os métodos, incluindo o do Liam (de 80.9% para 54.4% de Dice).
5. **Uma só referência** para os 30 minutos da recolha de 5 de outubro, com a câmara a mexer-se até 16 px.
6. **Poucas fotos com contorno:** 5 nas fotos antigas, 48 nas novas.
7. **Partes pressionadas com menos força** são cortadas (a barriga do P).
8. **A combinação de ângulos** piora nas formas com peças separadas.
9. **Star:** má em todos os métodos.

---

## 12. Código

### 12.1 `src/tactile/detect_shape.py` (alterado)
Cerca de 140 linhas alteradas, quase todas acrescentadas. O código completo das funções novas está no ficheiro e no relatório anterior (`docs/relatorio_segmentacao.md`, secção 6).
- **Imports:** `inverse_gaussian_gradient` e `morphological_geodesic_active_contour` do `skimage.segmentation`.
- **Configuração:** `STEM = None` (antes `"star"`), `BW_FRAC = 0.55`, `GAC_SIGMA_FRAC = 0.0026`, `GAC_ITERS = 20`, `DISP_BG_MARGIN_FRAC = 0.052`, `DISP_SMOOTH_FRAC = 0.0052` e `CONTACT_PARAMS`.
- **Funções novas:** `refine_contour(mask, score, roi, carrier, iters)` e `compensate_displacement(mask, dphi, carrier, roi, alpha)`.
- **`detect()`:** argumentos novos `bw_frac`, `smooth_frac`, `tight_lo_frac`, `refine` e `disp_alpha`, todos com os valores antigos por omissão. São passados à demodulação, à suavização e ao corte tight. No fim aplicam-se o encaixe da borda e a compensação.
- **Linha de comandos:** `--reference`, `--deformed`, `--stem` e `--contact`.

### 12.2 Ficheiros novos
| ficheiro | o que faz |
|---|---|
| `src/tactile/detect_shape_liam_original.py` | cópia exata do original do Liam |
| `src/tactile/adjust_photos.py` | alinhamento + ajuste de brilho/contraste |
| `verification/eval_segmentation.py` | avaliação nas fotos antigas (+ `--search` LOSO) |
| `verification/segment_photos_v2.py` | segmentação das fotos rodadas sem contorno |
| `verification/compare_adjustment.py` | segmentação com e sem ajuste, lado a lado |
| `verification/fuse_angles.py` | combinação de ângulos com o molde do Liam |
| `verification/build_dataset_v3.py` | montagem do conjunto anotado v3 |
| `verification/eval_photos_v3.py` | avaliação das 48 fotos com os contornos + combinação |
| `verification/compare_methods_table.py` | tabela de todos os métodos |
| `verification/show_adjusted.py` | imagens antes/depois do ajuste |
| `docs/relatorio_segmentacao.md` | relatório de 8 de outubro |
| `docs/relatorio_segmentacao_v2.md` | este relatório |

---

## 13. Dados, resultados e figuras

| pasta | conteúdo |
|---|---|
| `data/raw/shape_pictures/` | fotos antigas do Liam (inalteradas) |
| `data/raw/shape_pictures_v2/` | 48 fotos de 5 de outubro + referência, tal como recolhidas |
| `data/raw/shape_pictures_v3/` | as mesmas, com os Three Circles corrigidos e a foto de 0° reconstruída |
| `data/annotations/shape_pictures_v3/` | os 48 contornos desenhados por mim |
| `data/processed/shape_pictures_v2/` e `_v3/` | fotos alinhadas e ajustadas (106 MB cada, geradas pelo script) |
| `results/images_report/` | figuras originais do Liam |
| `results/segmentation_v2/shape_pictures/` | fotos antigas: tabela + figuras por forma + resumo |
| `results/segmentation_v2/shape_pictures_v2/` | fotos novas sem contorno: segmentação, brilho/contraste, combinação com molde |
| `results/segmentation_v2/shape_pictures_v3/` | fotos novas com contorno: `eval_photos_v3.csv`, figuras por forma, antes/depois |
| `results/segmentation_v2/method_comparison.*` | tabela de todos os métodos |
| `figures/` | figuras dos audits anteriores de força e temperatura, e cópias antigas |

**Figuras recomendadas para o relatório:**
- `results/segmentation_v2/method_comparison.png`: todos os métodos;
- `results/segmentation_v2/shape_pictures/figures/summary.png` e `Square_img_02.png`: fotos antigas;
- `results/segmentation_v2/shape_pictures_v3/before_after/overview.png`: o ajuste de brilho/contraste;
- `results/segmentation_v2/shape_pictures_v3/figures/F_shape.png`: fotos novas, uma foto sozinha e combinada;
- `results/segmentation_v2/shape_pictures_v2/fusion/Star.png`: como funciona a combinação.

---

## 14. Como reproduzir

```bash
cd ~/master_thesis
source .venv/bin/activate

# fotos antigas
python verification/eval_segmentation.py
python verification/eval_segmentation.py --search                 # opcional, 5–10 min

# fotos novas com contorno (v3)
python src/tactile/adjust_photos.py data/raw/shape_pictures_v3 data/processed/shape_pictures_v3
python verification/show_adjusted.py
python verification/eval_photos_v3.py
python verification/compare_methods_table.py

# uma foto sozinha
python src/tactile/detect_shape.py --contact --reference "data/raw/shape_pictures/Star/img_01.jpg" --deformed "data/raw/shape_pictures/Star/img_02.jpg"
```

---

## 15. Pendentes e próximos passos

1. **Corrigir a ordem no `refine_contour`** (suavizar antes de limpar). Tira a mancha do P e não muda os números.
2. **Guardar no git:** repor o `.gitignore` (excluir `.venv/` e `data/processed/*`) e fazer o commit.
3. **Confirmar com o supervisor** se os 80% são em Dice (já atingidos nas fotos antigas) ou em IoU.
4. **Desenvolver a segmentação pela variação do período** para o meu setup, como versão nova, e testá-la nas 48 fotos anotadas.
5. **Escolher o corte automaticamente** consoante o setup.
6. **Melhorar a combinação nas formas com várias peças**, alinhando cada peça separadamente.
7. **Próximas recolhas:** uma referência imediatamente antes de cada toque, a mesma resolução e zoom em todas as fotos, toques a direito com força constante e pausa entre toques. Para subir o contraste: tapar a luz direta dos LEDs à lente, foco manual, exposição manual, resolução máxima.

---

## 16. Notas

- **Audits antigos** (`audit_shape.py`, `audit_images_V3.py`, e `stripe_period_fft` em `estimate_force_depth.py`): apagam uma zona à volta do centro do espetro (`dc_r = N//40`) que esconde a frequência fundamental das riscas. Os "25.2 px" de período nos CSVs são a **3.ª harmónica**; o período real é ~75 px. O rácio usado para a força não é afetado, mas as conclusões dos audits sobre o período devem ser revistas.
- **Trabalho anterior** (não alterado): os audits de força, temperatura e fotos, em `verification/audit_*.py`, `plot_force.py`, `audit_*.csv` e `figures/force_*.png` / `temp_*.png`.
- **Página de resumo da reunião de 29 de setembro:** https://claude.ai/artifact/7VSEomPUFWABPYA3RjKq4r. Cobre só as fotos antigas.
- **Regra de versões:** nenhum ficheiro ou resultado anterior foi apagado. Cada mudança que altera resultados tem uma versão nova (`_v2`, `_v3`).
