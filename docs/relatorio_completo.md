# Relatório completo: verificação dos dados (audits) e segmentação de formas

Luís Campos · branch `luis/baseline-validation` · 15 de outubro de 2026

Este documento junta **todo o trabalho feito até hoje**, por ordem e com todos os números:
- **Parte I:** a verificação dos dados do Liam (audits de força, formas e temperatura), feita em setembro;
- **Parte II:** a segmentação de formas, feita de setembro a outubro;
- **Parte III:** limitações, correções, código, ficheiros, comandos e pendentes.

Os relatórios anteriores ficam guardados sem alterações:
- `docs/relatorio_segmentacao.md` (8 de outubro);
- `docs/relatorio_segmentacao_v2.md` (15 de outubro, só a segmentação).

**Verificação dos números da Parte I:** voltei a correr hoje os quatro scripts dos audits, com a saída numa pasta temporária para não escrever por cima dos ficheiros originais. Os quatro CSVs saíram idênticos, valor a valor, aos que estão em `verification/`. Os valores são percentagens, salvo indicação em contrário.

---

## 0. Resumo

### Parte I: verificação dos dados
1. **Fotos de força** (85 fotos: 16 níveis de 3 a 48 N com 5 fotos cada, mais 5 de referência). Nenhuma foto tem problemas de qualidade (0/85 alertas). O período das riscas sobe de 25.16 px (3 N) para 25.83 px (48 N), um sinal de **2.63%**, contra um ruído de **0.029%** entre fotos do mesmo nível. Isto dá uma razão sinal/ruído de 91 e cerca de 30 níveis distinguíveis.
2. **O sensor satura.** A sensibilidade cai de ~26 para ~7 milésimos de píxel por newton do início para o fim da gama. Os níveis 45 N e 48 N não se distinguem: o passo é de 0.0015 px, contra um σ de 0.0133 px. Acima de 33 N, 3 dos 5 passos de 3 N ficam abaixo do ruído.
3. **O modelo linear do Liam** (rácio de largura das riscas contra força), aplicado aos seus próprios pontos de calibração, erra até **2.8 N** (erro médio 0.85 N, RMSE 1.11 N). Os erros formam um arco, que é o padrão de uma reta ajustada a uma curva.
4. **A referência das fotos de força é diferente das outras fotos:**
   - o salto da referência para 3 N é de 0.19 px, 5 vezes um passo normal;
   - a nitidez é menor (158, contra 204–298);
   - o contraste das riscas é menor (0.24, contra 0.32).
5. **Temperatura** (2 peles × 4 corridas × 17–18 temperaturas):
   - a pele a cores só responde entre 24 e 33 °C, onde acontece 86–100% da variação de luminosidade;
   - a pele preto e cor responde em toda a gama de 24 a 75 °C (L\* de ~9–11 para ~63).
6. **Reprodutibilidade e histerese da temperatura:**
   - entre sessões, a diferença de cor é pequena (ΔE médio 1.0–1.9, ≈ 0.3–1.4 °C);
   - entre aquecimento e arrefecimento é muito maior (ΔE médio 5.5–8.8), 3 a 6 vezes a diferença entre sessões. A histerese é física, não ruído.
7. **Fotos de formas** (15 fotos, 7 formas): a qualidade chega para a FTP (0/15 alertas). As referências (`img_01`) têm todas o mesmo período (25.243 ± 0.008 px). Isto obriga a corrigir duas conclusões do audit:
   - os 4.44% de variação do período entre formas vêm das fotos pressionadas, não da câmara;
   - a área de contacto de ~49% é um artefacto do método (Otsu). A área real dos contornos é de 8 a 20% do disco da membrana.
8. **Os audits de força e de formas medem a 3.ª harmónica das riscas** (25.2 px), não a fundamental (~75 px). As variações relativas não mudam, mas o "período" nos CSVs não é o período real.
9. **Dois erros nos scripts dos audits:**
   - o `plot_force.py` deixou de correr (`k = 4.`);
   - o gráfico de sensibilidade da temperatura só desenha uma das quatro corridas.

   As figuras guardadas em `figures/` são anteriores a estas alterações e estão certas.

### Parte II: segmentação
10. **O código do Liam não tinha nenhuma medição da qualidade da segmentação.** Criei uma ferramenta que compara cada máscara com um contorno desenhado à mão (Dice, IoU, precisão do contorno a 1 mm, distâncias em mm).
11. **Fotos antigas** (5 fotos, câmara e contornos do Liam): o meu modo de contacto melhora todas as métricas face ao melhor modo do Liam (tight):
    - Dice de 80.9% para **82.9%**;
    - IoU de 68.0% para **71.0%**;
    - contorno a 1 mm de 51.4% para **67.2%**.
12. Estes números foram afinados nas mesmas 5 fotos. Em formas não vistas (validação *leave-one-shape-out*), o contorno a 1 mm fica em ~60%.
13. **Fotos novas** (48 fotos, 8 formas × 6 ângulos, câmara nova, contornos desenhados por mim): o meu método com corte a 15% dá **66.7%** de Dice, contra **54.4%** do tight do Liam. São +12.3 pontos, com melhoria em 40/48 fotos (p = 2×10⁻⁷).
14. **Combinar os 6 ângulos** dá **69.0%** de Dice, +2.4 pontos face a uma foto sozinha, sem significado estatístico (p = 0.13). Ajuda nas formas de uma só peça e piora nas formas com peças separadas.
15. **O ajuste de brilho/contraste** sugerido pelo supervisor melhora a aparência das fotos, mas **não muda a segmentação**: 37/47 fotos com o número certo de contactos, com e sem ajuste.
16. **Melhorar o setup** (enquadramento, exposição, luz) também não mudou o resultado. O contraste das riscas continua em metade do do Liam (0.28 contra 0.54).
17. **A diferença principal entre setups é física.** No setup do Liam, a zona pressionada aparece na fase como um planalto uniforme; no meu, como uma rampa. Isto depende da geometria da câmara, não da qualidade da foto.
18. No mapa de **variação do período das riscas**, as formas aparecem inteiras nas minhas fotos. É o sinal certo para o meu setup, mas um primeiro teste ainda não supera o método atual (59.6% contra 64.8% de Dice em 6 fotos).
19. **Meta de 80%:** já é atingida em Dice nas fotos antigas (82.9%). Falta confirmar com o supervisor se a meta é em Dice ou em IoU.

---

## 1. Contexto

### 1.1 O sensor e o código do Liam
- O sensor é uma membrana (pele) com um padrão de riscas, fotografada por uma câmara. Uma pressão desloca e deforma as riscas; os pigmentos da pele mudam de cor com a temperatura.
- O código do Liam Gibbons faz três medições:
  - **força e profundidade**, pela largura/período das riscas: `src/tactile/estimate_force_depth.py` e `src/tactile/uniform_reconstruct.py`;
  - **forma do contacto**, por FTP (*Fourier Transform Profilometry*): `src/tactile/detect_shape.py`;
  - **temperatura**, pela cor: `src/temperature/*.py`. O `src/integrated_pipeline.py` junta forma e temperatura.
- O último commit do Liam é o `5f63d96` ("fixed error in readme", 17 de agosto de 2026). A tese e a documentação das experiências estão em `docs/Gibbons_Liam_Master_Thesis.pdf` e `docs/Experiment Documentation.pdf`.

### 1.2 Ambiente de trabalho
- **Commit `4341688`** (14 de setembro de 2026, o único meu até agora): "Pin working environment". O `requirements.txt` fixa 19 pacotes:
  - numpy 2.5.3, scipy 1.18.1, pandas 3.0.5;
  - opencv-python 5.0.0.93, scikit-image 0.26.0, matplotlib 3.11.2, pillow 12.3.0;
  - mais as dependências destes.
- Python 3.12 num ambiente virtual em `.venv/`.
- No mesmo dia, às 09:17, o pipeline integrado foi corrido. A saída está em `output/temp_shape_recon/`: forma, interiores, reconstrução 3D, profundidade em mm (`.npy`) e segmentação da temperatura.
- Mais tarde instalei o `scikit-learn 1.9.1` no `.venv` para um teste (secção 13.5). Não está no `requirements.txt`.

### 1.3 Cronologia
Esta é a ordem real do trabalho, em hora local. As datas da Parte I vêm das datas dos ficheiros; as da Parte II, do registo das sessões de trabalho. **O relatório segue esta ordem.** A última coluna diz em que secção está cada passo.

| quando | o que foi feito | secção |
|---|---|---|
| **14 set**, 09:17 | ambiente fixado (commit `4341688`); pipeline integrado corrido | 1.2 |
| **16 set**, 19:03 | verificação visual do disco usado nos audits (`debug_mask.png`) | 3.2 |
| 16 set, 19:35–19:39 | audits corridos por esta ordem: força (figuras às 19:35), temperatura da pele a cores (19:36), temperatura da pele preto e cor (19:38), formas (19:38) | 3–6 |
| 16 set 20:46 – 17 set 00:36 | comentários acrescentados aos scripts dos audits | 2 |
| **17 set**, 09:25 | audit de força gravado outra vez (mesmos valores) | 3 |
| **25 set**, 09:26–09:58 | análise do código do Liam, diagnóstico, primeiras alternativas e plano | 11 |
| 25 set, 10:21–10:33 | teste rápido do encaixe da borda; comecei a aplicar as alterações | 12.1 |
| 25 set, 15:37–15:54 | apliquei o modo de contacto por blocos e verifiquei-o (regressão 30/30) | 12.1 |
| 25 set, 15:58–16:11 | ferramenta de avaliação, primeiros números e pesquisa LOSO; corri tudo no meu terminal | 10, 13.1 |
| 25 set, 16:14–16:42 | figuras antigo/novo, erro por orientação da borda, 17 variantes, meta de 80%, o que é o GT | 13.2–13.3 |
| 25 set, 16:56–17:07 | suavização final do contorno, Random Forest, CNN posta de parte, conclusão do dia | 13.4–13.7 |
| 25 set, 17:15–17:31 | formas sem contorno: mancha e barriga do P, Square Circle | 13.8 |
| **29 set**, 10:03–10:56 | preparação da reunião (página de resumo, comandos, resumo em pontos); reunião com o supervisor | 13.9 |
| **30 set**, 15:18–15:23 | planeamento das fotos novas: 6 ângulos, passos de 60° | 14.1 |
| **5 out**, 14:09–14:38 | recolha das 48 fotos rodadas e da referência | 14.2 |
| **6 out**, 16:55–17:13 | fotos importadas e medidas; primeira segmentação (sinal em rampa, foto em duplicado, corte a 15%) | 14.2–14.3 |
| 6 out, 17:26–18:20 | ajuste de brilho/contraste, segmentação das 48 fotos, regra das versões | 14.4 |
| 6 out, 18:22–18:40 | análise da diferença física do sinal; mensagem ao supervisor | 14.5–14.6 |
| 6 out, 23:24–23:59 | combinação dos 6 ângulos com o molde do Liam; decisão de desenhar os 48 contornos | 15 |
| 6 out 23:48 – 7 out 09:32 | desenhei os 48 contornos | 16.1 |
| **7 out**, 09:34–10:00 | conjunto v3, avaliação das 48 fotos e da combinação, tabela de todos os métodos, esclarecimentos | 16, 18 |
| 7 out, 14:55–15:02 | imagens antes/depois do ajuste de brilho/contraste | 14.4 |
| **8 out**, 09:29–09:41 | relatório v1 (`docs/relatorio_segmentacao.md`) | — |
| 8 out, 15:56–16:26 | setup melhorado: referência nova, dois toques no Square, mapa de variação do período | 17 |
| **12 out** | material dos slides intercalares (`results/midterm_slides/`) | 22.4 |
| **15 out**, 11:23–11:50 | relatório v2; audits corridos outra vez para confirmar os números; este relatório | — |

---

# PARTE I: Verificação dos dados (audits)

## 2. Objetivo e scripts

Antes de mexer nos algoritmos, verifiquei se os dados do Liam sustentam as conclusões dele. Os audits respondem a cinco perguntas:
- as fotos têm qualidade suficiente?
- as medições repetem-se?
- qual é a resolução da força?
- como se comporta a cor com a temperatura?
- os conjuntos de fotos são comparáveis entre si?

**Os audits medem as fotos, não avaliam os algoritmos.**

| script | dados | saída |
|---|---|---|
| `verification/audit_images_V3.py` | `data/raw/force_pictures/` | `verification/audit_force.csv` (85 linhas) |
| `verification/plot_force.py` | `audit_force.csv` + calibração do Liam | `figures/force_*.png` (4 figuras) |
| `verification/audit_temperature.py` | `data/raw/full_color_experiment/` e `black_and_color_experiment/` | `verification/audit_temp_*.csv` (210 linhas cada) + `figures/temp_*.png` (4 figuras) |
| `verification/audit_shape.py` | `data/raw/shape_pictures/` | `verification/audit_shape.csv` (15 linhas) |

Tempos de execução: força 48 s, formas 9 s, temperatura ~35 s por pele.

---

## 3. Fotos de força: audit (`audit_images_V3.py`)

### 3.1 Dados
- `data/raw/force_pictures/`: 17 pastas, 3N, 6N, …, 48N (passos de 3 N) e `reference`. Cada pasta tem 5 fotos.
- No total são **85 fotos** de 4608×3456 px.

### 3.2 Método (por foto)
| métrica | como é medida |
|---|---|
| **nitidez** | variância do Laplaciano dentro do disco da membrana, na foto reduzida a 800 px de largura |
| **saturação** | % de píxeis ≥ 250 (brancos) e ≤ 5 (pretos) no disco, em resolução total |
| **período das riscas** | FFT 2D de um recorte central de 1024×1024 px, com janela de Hann e *zero-padding* 4×. O pico é procurado fora de uma zona central (`dc_r = max(24, N//40)`) e refinado por interpolação parabólica. Período = 1024 / frequência do pico |
| **ângulo** | direção do pico no espetro |
| **SNR da portadora** | altura do pico / mediana do espetro |
| **modulação** | desvio-padrão da imagem passa-banda / média local (contraste das riscas) |
| **vinheta** | brilho médio no anel entre 70 e 95% do raio / brilho no centro (< 30% do raio) |

- **Disco da membrana:** raio = 0.60 × metade do lado menor (`ROI_FRACTION`). A posição está confirmada em `verification/debug_mask.png` (círculo vermelho dentro da membrana).
- **Alertas automáticos:**
  - `BLOWN_HIGHLIGHTS`: > 1% de píxeis brancos;
  - `CRUSHED_BLACKS`: > 1% de píxeis pretos;
  - `WEAK_CARRIER`: SNR < 8;
  - `UNEVEN_LIGHT`: vinheta fora de 0.80–1.20.
- **Pergunta principal:** o período muda mais entre níveis de força do que entre fotos do mesmo nível?

### 3.3 Resultados por nível
Período = média ± desvio-padrão das 5 fotos (populacional). CV = desvio / média.

| nível | período (px) | CV (%) | nitidez | SNR | modulação | vinheta |
|---|---|---|---|---|---|---|
| 3 N | 25.1644 ± 0.0044 | 0.0175 | 298.5 | 3007 | 0.325 | 1.140 |
| 6 N | 25.2490 ± 0.0041 | 0.0161 | 284.9 | 3046 | 0.325 | 1.138 |
| 9 N | 25.3250 ± 0.0024 | 0.0093 | 282.9 | 3029 | 0.325 | 1.137 |
| 12 N | 25.4019 ± 0.0011 | 0.0043 | 276.9 | 3047 | 0.325 | 1.135 |
| 15 N | 25.4528 ± 0.0049 | 0.0193 | 271.5 | 3034 | 0.325 | 1.133 |
| 18 N | 25.5081 ± 0.0076 | 0.0298 | 265.6 | 3032 | 0.326 | 1.134 |
| 21 N | 25.5455 ± 0.0042 | 0.0166 | 257.7 | 3033 | 0.326 | 1.134 |
| 24 N | 25.5822 ± 0.0016 | 0.0062 | 254.5 | 3000 | 0.326 | 1.133 |
| 27 N | 25.6284 ± 0.0075 | 0.0292 | 251.7 | 2957 | 0.326 | 1.133 |
| 30 N | 25.6642 ± 0.0099 | 0.0385 | 243.5 | 2930 | 0.325 | 1.132 |
| 33 N | 25.7008 ± 0.0089 | 0.0345 | 237.2 | 2905 | 0.324 | 1.131 |
| 36 N | 25.7268 ± 0.0149 | 0.0579 | 230.1 | 2873 | 0.323 | 1.131 |
| 39 N | 25.7641 ± 0.0018 | 0.0070 | 222.8 | 2829 | 0.322 | 1.128 |
| 42 N | 25.7993 ± 0.0079 | 0.0308 | 216.9 | 2809 | 0.321 | 1.128 |
| 45 N | 25.8250 ± 0.0133 | 0.0516 | 208.4 | 2731 | 0.319 | 1.126 |
| 48 N | 25.8265 ± 0.0119 | 0.0461 | 204.4 | 2677 | 0.318 | 1.126 |
| **referência** | **24.9728 ± 0.0018** | 0.0070 | **158.0** | **2588** | **0.241** | **1.111** |

### 3.4 Resumo do audit
- **Sinal** (variação total do período, incluindo a referência): **3.418%**.
- **Ruído** (CV médio dentro de cada pasta): **0.0248%**.
- **Sinal/ruído: 138**, ou seja, ~**46 níveis** distinguíveis com separação de 3σ.
- **Alertas: 0/85.** Não há saturação (no máximo 0.0008% de píxeis brancos), a portadora é forte (SNR entre 2573 e 3080 em todas as fotos, contra o mínimo de 8) e a luz é uniforme (vinheta entre 1.111 e 1.142).
- Nenhuma pasta tem CV acima de 0.1% (o limite para "ruidosa"). As maiores são 36 N (0.058%) e 45 N (0.052%).

### 3.5 Observações
- **A nitidez desce com a força,** de 298 (3 N) para 204 (48 N), −32%. O SNR desce 11% (3007 → 2677), e a modulação fica constante (0.318–0.326). A causa pode ser a deformação maior da membrana, que distorce as riscas, ou uma deriva do foco ao longo da sessão; estes dados não permitem separar as duas.
- **A referência é diferente das outras pastas:**
  - nitidez 158;
  - modulação 0.241, contra 0.318–0.326;
  - SNR 2588;
  - período 0.19 px abaixo dos 3 N, cerca de 5 vezes um passo normal.

  Indica que a referência foi tirada em condições diferentes (outra sessão, foco ou luz).
- **Ângulo das riscas:** −147.6° a −148.7° em todas as fotos. A média dos 9 N aparece como −111.7° porque uma foto apanhou o pico simétrico do espetro (+32.35° = −147.65° + 180°). É a mesma orientação.

---

## 4. Fotos de força: análise e figuras (`plot_force.py`)

### 4.1 Números principais (sem a referência)
| | valor |
|---|---|
| níveis de força | 16 (3–48 N) |
| período da referência | 24.9728 px |
| **sinal** (variação do período, 3 → 48 N) | **2.631%** |
| **ruído** (CV médio dentro de cada nível) | **0.0290%** |
| sinal/ruído | 91 |
| níveis distinguíveis (3σ) | **30** |
| salto referência → 3 N | +0.1916 px |
| passo típico (mediana) | +0.0373 px |
| último passo (45 → 48 N) | +0.0015 px, contra σ = 0.0133 px |

- **O script dá dois alertas:**
  - "o primeiro passo é anormalmente grande, verificar a referência" (0.1916 contra 0.0373, mais do dobro);
  - "45 N e 48 N NÃO são distinguíveis" (o passo é menor do que 3σ).
- **Porque é que estes valores diferem dos do audit** (3.418% / 0.0248% / 46 níveis):
  - o audit inclui a pasta de referência no sinal e no ruído, e usa o desvio-padrão populacional;
  - o `plot_force.py` exclui a referência e usa o desvio-padrão amostral.

  Para "resolução de força entre 3 e 48 N", o número certo é o do `plot_force.py`: **2.631%, ~30 níveis**.

### 4.2 Passo a passo
Calculei, para cada par de níveis seguidos, o passo do período, o ruído (3σ, com σ = média dos dois níveis) e a sensibilidade. São as mesmas fórmulas das figuras `force_noise` e `force_sensitivity`.

| intervalo | passo (px) | 3σ (px) | sensibilidade (milésimos de px/N) | distinguível? |
|---|---|---|---|---|
| 3 → 6 N | 0.0846 | 0.0142 | 28.2 | sim |
| 6 → 9 N | 0.0760 | 0.0108 | 25.3 | sim |
| 9 → 12 N | 0.0769 | 0.0058 | 25.6 | sim |
| 12 → 15 N | 0.0509 | 0.0101 | 17.0 | sim |
| 15 → 18 N | 0.0553 | 0.0210 | 18.5 | sim |
| 18 → 21 N | 0.0374 | 0.0199 | 12.5 | sim |
| 21 → 24 N | 0.0368 | 0.0098 | 12.3 | sim |
| 24 → 27 N | 0.0461 | 0.0152 | 15.4 | sim |
| 27 → 30 N | 0.0358 | 0.0291 | 11.9 | sim (à justa) |
| 30 → 33 N | 0.0366 | 0.0314 | 12.2 | sim (à justa) |
| 33 → 36 N | 0.0260 | 0.0399 | 8.7 | **não** |
| 36 → 39 N | 0.0373 | 0.0280 | 12.4 | sim |
| 39 → 42 N | 0.0352 | 0.0163 | 11.7 | sim |
| 42 → 45 N | 0.0257 | 0.0357 | 8.6 | **não** |
| 45 → 48 N | 0.0015 | 0.0423 | 0.5 | **não** |

- **Até 33 N, todos os passos de 3 N se distinguem.** Acima de 33 N, 3 dos 5 passos ficam abaixo do ruído.
- Os "30 níveis" são uma média sobre toda a gama. A resolução real é boa em forças baixas e pior em forças altas.

### 4.3 Saturação
- A sensibilidade média é de **26.4** milésimos de px/N nos três primeiros intervalos (3–12 N) e de **6.9** nos três últimos (39–48 N): cai cerca de 4 vezes. No último intervalo é quase zero (0.5).
- **O período não varia linearmente com a força:**

  | ajuste | erro RMS | erro máximo |
  |---|---|---|
  | reta | 0.0379 px | 0.0865 px |
  | parábola | **0.0109 px** | 0.0203 px |

  O erro da parábola fica ao nível do ruído (~0.01 px), por isso a curvatura é real. A parábola é período = 25.110 + 0.02519·F − 0.000213·F².
- Na figura `force_period_vs_load`, a reta dos primeiros 4 pontos afasta-se cada vez mais dos dados a partir de ~15 N.

### 4.4 O modelo linear do Liam, testado nos seus próprios pontos
- **Dados de calibração do Liam:** `data/processed/csv_files/force_vs_mean_width_ratio_frequency.csv`. É o rácio médio de largura das riscas (pressionada / referência) para cada força, com 3 fotos por nível, de 3 a 48 N. O rácio vai de 1.0052 a 1.0323.
- **Reta ajustada:** rácio = 1.005056 + 0.000586·F, com **R² = 0.9936**.
- **Invertendo a reta** (rácio → força, que é o que o pipeline faz) e aplicando-a aos mesmos pontos:

| força real (N) | 3 | 6 | 9 | 12 | 15 | 18 | 21 | 24 | 27 | 30 | 33 | 36 | 39 | 42 | 45 | 48 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| erro (N) | **−2.80** | −0.88 | +0.20 | +0.29 | +1.12 | +1.43 | +0.36 | +0.82 | +0.14 | +1.28 | +1.11 | −0.24 | +0.04 | −0.11 | −1.25 | −1.51 |

- **Erro máximo 2.80 N** (a 3 N, 93% do valor), erro médio absoluto **0.85 N**, **RMSE 1.11 N**.
- **O erro tem a forma de um arco:** é negativo nas pontas (3–6 N e 45–48 N) e positivo no meio (15–33 N). É o padrão de uma reta ajustada a uma curva que satura. O R² alto (0.994) esconde isto.
- Estes erros são medidos nos pontos usados para ajustar a reta, por isso são o melhor caso possível. Em fotos novas, o erro seria igual ou maior.

### 4.5 Figuras (16 de setembro)
| ficheiro | o que mostra |
|---|---|
| `figures/force_period_vs_load.png` | período contra força com barras de erro; linha da referência; reta dos 4 primeiros pontos, para mostrar a saturação |
| `figures/force_linearity.png` | erro do modelo linear do Liam nos seus pontos (barras a vermelho quando o erro > 1 N) |
| `figures/force_sensitivity.png` | sensibilidade (milésimos de px/N) contra força |
| `figures/force_noise.png` | passo entre níveis contra 3σ do ruído; onde a linha entra na zona sombreada, os níveis deixam de se distinguir |

### 4.6 Erro no script atual
- **Na linha 87, `k = 4.`** (com ponto, um número decimal). Com o pandas 3.0.5 fixado no ambiente, `g.force_N[:k]` dá `TypeError` e o script para antes de gravar as figuras.
- As figuras de 16 de setembro foram feitas antes desta alteração.
- Com `k = 4`, as quatro figuras saem iguais às guardadas. A única diferença é a pontuação de um título. Verifiquei isto numa cópia do script, na pasta temporária.
- A correção está na secção 24.

---

## 5. Temperatura: audit (`audit_temperature.py`)

### 5.1 Dados
- **Duas peles:** `full_color_experiment` (pele a cores) e `black_and_color_experiment` (pele preto e cor).
- **4 corridas por pele:** Heating Run, Heating Run 2, Cooling Run e Cooling Run 2 (aquecimento e arrefecimento, duas sessões cada).
- **Temperaturas da cama:**
  - de 24 a 32 °C, de 1 em 1 °C;
  - de 35 a 70 °C, de 5 em 5 °C;
  - as corridas de aquecimento têm também 75 °C.

  São 17 temperaturas no arrefecimento e 18 no aquecimento.
- 10 fotos por temperatura, ou seja 700 por pele, de 4608×3456 px. **O audit usa as 3 primeiras** de cada temperatura (`--max-per-folder 3`), ou seja 210 fotos por pele.

### 5.2 Método
- **Cor média em CIELAB** num disco central de raio 0.45 (`DISC_FRACTION`, menor do que o 0.60 da força). As grandezas medidas são:
  - L\* (luminosidade, 0–100), a\*, b\*;
  - croma = √(a\*² + b\*²);
  - desvio de L\*, médias RGB e saturação.
- **Diferença de cor:** ΔE CIE76, a distância euclidiana em LAB. Valores de referência:
  - ≈ 1: quase impercetível;
  - \> 3: claramente diferente;
  - \> 10: cores obviamente diferentes.
- **Três testes:**
  1. **Monotonia:** fração dos passos de temperatura em que L\* vai no sentido dominante.
  2. **Reprodutibilidade entre sessões:** corrida 1 contra corrida 2 à mesma temperatura (ΔE médio e máximo). Inclui também um erro de temperatura aparente, igual à mediana de ΔE / |dL\*/dT|.
  3. **Histerese:** aquecimento contra arrefecimento da mesma sessão, à mesma temperatura.

### 5.3 Pele a cores (`full_color_experiment`)
**Monotonia** (L\* a 24 °C → L\* à temperatura máxima):

| corrida | L\* | variação | monotonia | passos em que L\* desce |
|---|---|---|---|---|
| Heating Run | 40.31 → 62.39 | 24.61 | 76% | 4 de 17: 35→40, 50→55 (−2.54), 55→60, 65→70 |
| Heating Run 2 | 39.60 → 63.52 | 23.92 | 88% | 2 de 17: 40→45, 60→65 |
| Cooling Run | 44.66 → 63.27 | 18.60 | 81% | 3 de 16: 30→31 (−0.70), 35→40, 40→45 |
| Cooling Run 2 | 43.52 → 62.22 | 19.46 | 69% | 5 de 16: 30→31 (−1.19), 31→32, 35→40, 55→60, 65→70 |

- **Cor:** a 24 °C a pele tem um tom arroxeado (a\* +8 a +12, b\* −16 a −20, croma 19–22). Acima de ~33 °C fica cinzenta (croma 1–2).
- **Onde responde:** 86–100% da variação de L\* acontece até 33 °C (Heating 86%, Heating 2 93%, Cooling 95%, Cooling 2 100%).
  - A sensibilidade máxima é de 4.4 a 7.9 L\*/°C, entre 25 e 32 °C.
  - Acima de 33 °C é de apenas 0.10–0.22 L\*/°C.
  - Quase todos os passos em que L\* desce estão nesta zona plana, onde o ruído pesa mais. A exceção é 30→31 °C nas duas corridas de arrefecimento.

**Reprodutibilidade entre sessões:**

| comparação | ΔE médio | ΔE máximo | erro aparente | só 24–32 °C |
|---|---|---|---|---|
| Cooling vs Cooling 2 | 1.57 | 6.02 (a 25 °C) | 1.9 °C | 1.0 °C |
| Heating vs Heating 2 | 1.88 | 5.06 (a 30 °C) | 4.7 °C | **0.8 °C** |

Os 4.7 °C estão inflacionados: acima de 33 °C a cor quase não muda, e dividir um ΔE pequeno por um declive quase nulo dá erros enormes. Na zona útil (24–32 °C), o erro aparente é de **0.8–1.0 °C**.

**Histerese:**

| comparação | ΔE médio | ΔE máximo |
|---|---|---|
| Heating vs Cooling | **8.79** | 24.26 (a 29 °C) |
| Heating 2 vs Cooling 2 | **7.07** | 19.50 (a 30 °C) |

### 5.4 Pele preto e cor (`black_and_color_experiment`)
**Monotonia:**

| corrida | L\* | variação | monotonia | passos em que L\* desce |
|---|---|---|---|---|
| Heating Run | 8.56 → 63.10 | 54.55 | 94% | 1 de 17: 70→75 (−0.01) |
| Heating Run 2 | 8.55 → 63.73 | 55.17 | **monotónica** | nenhum |
| Cooling Run | 11.01 → 62.29 | 51.28 | **monotónica** | nenhum |
| Cooling Run 2 | 10.98 → 62.63 | 52.56 | 94% | 1 de 16: 65→70 (−0.91) |

- **Cor:** quase neutra (croma 4–5 a 24 °C, 0–1 no fim). A mudança é sobretudo em luminosidade, de escuro para claro, com uma variação de 51–55 L\*, mais do dobro da pele a cores.
- **Onde responde:** só 25–36% da variação acontece até 33 °C. Acima disso, continua a ~0.9–1.0 L\*/°C. **Responde em toda a gama, de 24 a 75 °C.** A sensibilidade máxima é de 3.3–4.5 L\*/°C, entre 27.5 e 31.5 °C.

**Reprodutibilidade entre sessões:**

| comparação | ΔE médio | ΔE máximo | erro aparente | só 24–32 °C |
|---|---|---|---|---|
| Cooling vs Cooling 2 | **0.97** | 2.30 (a 65 °C) | **0.4 °C** | 0.3 °C |
| Heating vs Heating 2 | 1.90 | 3.20 (a 65 °C) | 1.4 °C | 1.3 °C |

**Histerese:**

| comparação | ΔE médio | ΔE máximo |
|---|---|---|
| Heating vs Cooling | **5.89** | 12.67 (a 65 °C) |
| Heating 2 vs Cooling 2 | **5.48** | 14.68 (a 65 °C) |

### 5.5 Conclusões da temperatura
- **O ruído entre fotos da mesma temperatura é desprezável:** o desvio médio de L\* é de 0.049 (pele a cores) e 0.010 (preto e cor). Não há píxeis saturados (0%).
- **A histerese é 3 a 6 vezes maior do que a diferença entre sessões:**
  - pele a cores: 7.1–8.8 contra 1.6–1.9;
  - pele preto e cor: 5.5–5.9 contra 1.0–1.9.

  Duas sessões independentes concordam muito melhor do que o aquecimento com o arrefecimento, por isso a diferença é **física**: os pigmentos não seguem o mesmo caminho a aquecer e a arrefecer. Uma calibração única terá erros sistemáticos, a não ser que saiba se a pele está a aquecer ou a arrefecer.
- **A pele a cores só serve para 24–33 °C** (erro aparente de ~1 °C nessa zona). **A pele preto e cor serve para 24–75 °C** (0.3–1.4 °C) e é a mais fiável.

### 5.6 Figuras (16 de setembro)
| ficheiro | o que mostra |
|---|---|
| `figures/temp_full_color_experiment_curves.png` | L\* e croma contra temperatura, 4 corridas (sessão 2 a tracejado) |
| `figures/temp_full_color_experiment_sensitivity.png` | \|dL\*\| por grau, 4 corridas: resposta só entre 24 e 32 °C |
| `figures/temp_black_and_color_experiment_curves.png` | o mesmo para a pele preto e cor |
| `figures/temp_black_and_color_experiment_sensitivity.png` | o mesmo para a pele preto e cor: resposta em toda a gama |

### 5.7 Erro no script atual
- **Na linha 312**, a instrução `ax.plot(mid, dL, ...)` do gráfico de sensibilidade ficou fora do ciclo `for`. Por isso só a última corrida (Heating Run 2) é desenhada.
- As figuras de 16 de setembro têm as 4 corridas, porque foram feitas antes desta alteração. Comparei a figura guardada com a que o script faz agora.
- Os CSVs e os números impressos não são afetados.
- A correção está na secção 24.

---

## 6. Fotos de formas: audit (`audit_shape.py`)

### 6.1 Dados
- `data/raw/shape_pictures/`: 7 formas e **15 fotos**. O F tem 3 fotos; o P, Ring, Square, Square Circle, Star e Three Circles têm 2 cada.
- `img_01` é a referência (sem pressão); `img_02` e `img_03` são fotos pressionadas.
- Há 5 contornos desenhados (`*_gt.jpg`): F, Ring, Square, Star e Three Circles.

### 6.2 Método
- As mesmas métricas do audit de força, com o mesmo disco de 0.60, para os dois conjuntos serem comparáveis.
- Mais a fração da área de contacto, calculada nos contornos com um limiar automático de Otsu.

### 6.3 Resultados por forma
| forma | n | período (px) | SNR | modulação | nitidez | vinheta | saturação |
|---|---|---|---|---|---|---|---|
| F | 3 | 29.10 | 2265 | 0.32 | 135.2 | 1.14 | 0.00 |
| P | 2 | 26.36 | 1924 | 0.30 | 136.8 | 1.18 | 0.00 |
| Ring | 2 | 25.41 | 2031 | 0.36 | 154.4 | 1.19 | 0.00 |
| Square | 2 | 25.53 | 1692 | 0.27 | 117.8 | 1.12 | 0.00 |
| Square Circle | 2 | 25.80 | 1965 | 0.33 | 153.4 | 1.17 | 0.00 |
| Star | 2 | 26.66 | 1727 | 0.33 | 135.1 | 1.19 | 0.00 |
| Three Circles | 2 | 25.99 | 1696 | 0.30 | 137.4 | 1.17 | 0.00 |

- **Consistência entre formas** (média e variação entre as 7 médias):
  - período 26.407 px, variação **4.44%**;
  - SNR 1900, variação 10.33%;
  - modulação 0.317, variação 8.54%;
  - vinheta 1.164, variação 1.88%.
- **Comparação com a força:**

  | conjunto | período | modulação | SNR |
  |---|---|---|---|
  | força (todas) | 25.537 | 0.319 | 2913 |
  | força (referência) | 24.973 | 0.241 | 2588 |
  | formas (todas) | 26.587 | 0.317 | 1925 |

- **Alertas: 0/15.**

### 6.4 Releitura com os valores de cada foto
O audit compara médias por forma, que misturam referências e fotos pressionadas. Separando as duas:

| grupo | n | período (px) | CV | SNR | modulação | nitidez |
|---|---|---|---|---|---|---|
| **formas: referências (`img_01`)** | 7 | **25.243 ± 0.008** | **0.032%** | 2417 | 0.316 | 132.0 |
| formas: pressionadas | 8 | 27.763 ± 2.037 | 7.3% | 1494 | 0.319 | 143.9 |
| força: referência | 5 | 24.973 ± 0.002 | 0.007% | 2588 | 0.241 | 158.0 |
| força: com carga | 80 | 25.573 ± 0.202 | 0.79% | 2934 | 0.324 | 250.5 |

Período de cada foto (referência / pressionada):

| F | P | Ring | Square | Square Circle | Star | Three Circles |
|---|---|---|---|---|---|---|
| 25.237 / 30.951 / 31.108 | 25.236 / 27.483 | 25.262 / 25.558 | 25.241 / 25.810 | 25.241 / 26.366 | 25.241 / 28.082 | 25.242 / 26.746 |

**Conclusões que corrigem a leitura anterior:**
- **As 7 referências têm o mesmo período, a 0.03% umas das outras.** Os 4.44% de variação entre formas vêm das fotos pressionadas: a fase muda 3–10 rad nas fotos de formas, contra ≤ 0.2 rad nas de força, e isso altera o espetro do recorte central.
- **O comentário no `audit_shape.py` não se confirma.** Diz que a variação "só pode vir de outra distância da câmara, zoom ou pele", mas a câmara e a pele estão iguais em todas as pastas de formas.
- **Para comparar os dois conjuntos, devem usar-se as referências.**
  - O período das formas é **+1.08%** maior (25.243 contra 24.973 px). É uma diferença real, mas pequena: pode ser distância, zoom ou tensão da membrana entre sessões.
  - O contraste das riscas é maior nas referências de formas (0.316 contra 0.241), o que confirma outra vez que a referência de força é a fotografia "estranha".
- **O SNR desce nas fotos pressionadas** (1017–2268, contra 1960–2729 nas referências), porque o contacto espalha o pico das riscas.

### 6.5 Área de contacto: correção
- O audit mostra que o contacto cobre **48.3–49.9%** do disco nas 5 formas (F 49.4, Ring 49.9, Square 49.1, Star 48.8, Three Circles 48.3).
- **Isto é um artefacto.** O Otsu em cinzento separa as riscas claras das escuras, que ocupam cerca de metade cada, e não lê o contorno vermelho.
- **Medi a área real** com os contornos vermelhos, pelo mesmo método da Parte II. O disco de análise da segmentação tem 58.6 mm de diâmetro e 2695 mm²:

| forma | área do contorno | % do disco |
|---|---|---|
| F | 456 mm² | 16.9% |
| Ring | 530 mm² | 19.7% |
| Square | 508 mm² | 18.8% |
| Star | 394 mm² | 14.6% |
| Three Circles | 212 mm² | 7.9% |

  O disco do audit (0.60 da foto inteira) não é o mesmo que o da segmentação (0.45 do recorte), por isso as percentagens não são diretamente comparáveis. Mas a ordem de grandeza é de 8 a 20%, não ~49%.
- Foi também por isto que criei a ferramenta de avaliação da Parte II: este audit não lê os contornos nem avalia o algoritmo.

---

## 7. Problema comum aos audits de força e formas: a 3.ª harmónica

- **O que acontece:** para não apanhar o pico central do espetro, o código apaga uma zona à volta do centro, com `dc_r = max(24, N//40)`. Com N = 4096 (recorte de 1024 com *padding* 4×), são 102 posições, ou seja 25.5 ciclos por 1024 px. Isto **esconde tudo o que tenha período acima de ~40 px**.
- **O período real das riscas** é de ~75–77 px nas fotos de 4608 px, ou seja ~13.5 ciclos, dentro da zona apagada. O pico mais forte que sobra é a **3.ª harmónica**, a ~25.2 px (≈ 75.6 / 3). É esse o "período" que aparece nos CSVs.
- **O que não muda:** as variações relativas (o sinal de 2.631%, o ruído, os níveis distinguíveis, a comparação entre conjuntos). Esticar o padrão de riscas estica todas as harmónicas na mesma proporção.
- **O que muda:** o valor absoluto do "período" é um terço do real, e o SNR é o da 3.ª harmónica.
- **O mesmo está no pipeline de força do Liam,** em `estimate_force_depth.stripe_period_fft` (linha 94). O rácio que o pipeline usa não é afetado, pela mesma razão.

---

## 8. Conclusões da Parte I

1. **Força:** fotos com boa qualidade e boa repetibilidade (CV ≤ 0.06%).
   - O sinal é de 2.63% em 3–48 N, com cerca de 30 níveis distinguíveis em média.
   - O sensor satura: acima de 33 N, alguns passos de 3 N já não se distinguem, e 45 e 48 N são iguais.
   - Um modelo linear erra até 2.8 N nos próprios pontos de calibração. Um modelo curvo (por exemplo quadrático) é mais adequado.
   - A referência foi tirada em condições diferentes e deve ser revista.
2. **Temperatura:** cor estável dentro de cada temperatura e reprodutível entre sessões (ΔE 1–2).
   - A histerese é grande (ΔE 5.5–8.8) e física.
   - A pele a cores só é útil entre 24 e 33 °C; a pele preto e cor é útil em toda a gama.
3. **Formas:** as fotos chegam para a FTP, e as referências de todas as formas são consistentes entre si.
   - A variação de período entre formas vem do contacto, não da câmara.
   - A área de contacto do audit está errada (artefacto do Otsu).
   - O audit não avalia a segmentação, o que levou à Parte II.
4. **Audits de força e formas:** o "período" é a 3.ª harmónica. As conclusões relativas mantêm-se.

---

# PARTE II: Segmentação de formas

## 9. Ponto de partida

### 9.1 Objetivo
O supervisor pediu para melhorar a **segmentação das formas pressionadas na membrana** (o contorno de cada forma), com uma meta de cerca de 80%. Ainda falta confirmar se a meta se refere ao Dice ou ao IoU.

### 9.2 O código do Liam
- O original de `detect_shape.py` está guardado como `src/tactile/detect_shape_liam_original.py`, uma cópia exata do commit `5f63d96`.
- A segmentação está em `src/tactile/detect_shape.py`, na função `detect()`:
  1. recorte quadrado central (`CROP_RATIO = 0.31` do lado menor) e redimensionamento para 768×768 px (`PROC_SIZE`);
  2. demodulação FTP: encontra a portadora (o pico das riscas no espetro) e aplica um filtro passa-banda gaussiano com largura `BW_FRAC = 0.55` da frequência da portadora;
  3. diferença de fase entre a foto pressionada e a referência, desenrolada (`unwrap_phase`);
  4. filtro passa-alto (σ = 0.117 × 768 ≈ 90 px) e suavização (`SMOOTH_SIGMA_FRAC = 0.008`, ≈ 6 px);
  5. *z-score* robusto, limiar com histerese, morfologia, filtro de componentes e tratamento de buracos;
  6. dois modos:
     - **default (footprint)**: toda a zona deformada, incluindo o halo. É o modo usado pelo pipeline de força (`uniform_reconstruct.py`, com `CALIB_FOOTPRINT_SCALE = 1.874` calibrado sobre esta máscara);
     - **tight**: corta cada contacto a 35% do seu próprio pico (`TIGHT_LO_FRAC = 0.35`).
- Canais opcionais: `--use-orient` (orientação das riscas) e `--use-amp` (queda da amplitude das riscas).
- **Não existia nenhuma medição da qualidade da segmentação** (ver a secção 6.5).

### 9.3 Fotos antigas e contornos de referência (Liam)
- `data/raw/shape_pictures/<Forma>/`: `img_01.jpg` é a referência, `img_02.jpg` a foto pressionada e `*_gt.jpg` o contorno desenhado à mão a vermelho. As fotos têm 4608×3456 px.
- Há contornos para **F, Ring, Square, Star e Three Circles**. O P e o Square Circle não têm contorno; o F tem uma segunda foto (`img_03`) sem contorno exato.
- **Cada contorno foi desenhado sobre o `img_02` da mesma pasta:** os píxeis fora do vermelho são idênticos (diferença média 0.00). O contorno do Square tem 1 px a menos de largura (4607 px), o que é irrelevante.
- O traço vermelho tem 58–73 px na foto original (≈ 2 mm), ou seja ~24 px na imagem de trabalho de 768 px.
- **Escala:** 32.9 px/mm na foto original e **11.8 px/mm** na imagem de 768 px. Foi medida pelo círculo de calibração de 20 mm (314 mm², 43 713 px na imagem de 768).
- **Período real das riscas:** ~75–77 px na foto original (≈ 2.3 mm), ou 27.1 px na imagem de 768. Ângulo da portadora: −148°.

---

## 10. Ferramenta de avaliação e métricas

Script: `verification/eval_segmentation.py`. As métricas foram definidas na manhã de 25 de setembro, durante o diagnóstico (secção 11); o script foi escrito às 16:03 do mesmo dia.

**Leitura do contorno de referência (GT):**
1. vermelho = `R − max(G, B) > 70`, seguido de um fecho morfológico 9×9;
2. cada região fechada conta como objeto se estiver dentro de um número **ímpar** de contornos, o que deixa vazio o buraco do Ring;
3. os píxeis do traço são divididos pelo meio, para a fronteira ficar no centro da linha desenhada;
4. o contorno sofre o mesmo recorte e redimensionamento (768 px) que a foto.

**Métricas**, comparando a máscara detetada (P) com o GT (G):
- **Dice** = 2|P∩G| / (|P| + |G|);
- **IoU** = |P∩G| / |P∪G|. Mede o mesmo que o Dice numa escala mais exigente: Dice 80% = IoU 66.7%;
- **precisão e recall** da área;
- **contorno a X mm (F@Xmm):** média harmónica entre duas frações: a da borda detetada a menos de X mm da borda verdadeira e a da borda verdadeira a menos de X mm da detetada. Calculei para 0.5, 1 e 2 mm;
- **ASSD:** distância média entre as duas bordas, em mm;
- **HD95:** distância a 95% entre as bordas, em mm;
- **número de contactos** (peças separadas).

**Estatística:** teste de Wilcoxon emparelhado, que compara os dois métodos na mesma foto.

**Validação *leave-one-shape-out* (LOSO):** escolher os parâmetros com 4 formas e testar na 5.ª, repetindo para cada forma.

---

## 11. Fase A: diagnóstico do método do Liam (25 set, manhã; fotos antigas)

### 11.1 Resultados de partida
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

- **Default:** recall de ~100%, mas precisão de só 35–72%, porque inclui o halo à volta do objeto. Serve o pipeline de força, não a forma.
- **Tight:** HD95 ≈ 44 px (≈ 3.7 mm).

### 11.2 O que o diagnóstico mostrou
- **Sobre o contacto, a fase forma uma lomba positiva:** 93–100% dos píxeis do GT têm z > +2, e a borda do GT fica a 72–92% da altura do planalto.
- **O "modo dipolo" do código nunca é ativado** (`w_opp = 0` nas 5 fotos), por isso o canal de *strain* nunca é usado. Usar o gradiente da fase como sinal dá IoU de 5–30%, porque só marca bordas.
- **Os canais opcionais pioram:**

  | variante | IoU | contorno 1 mm |
  |---|---|---|
  | tight | 68.0 | 52.1 |
  | tight + orientação | 61.7 | 34.7 |
  | tight + amplitude | 48.8 | 32.1 |
  | tight + os dois | 45.5 | 23.0 |

- **Teto de anotação** (comparar o GT com ele próprio deslocado):
  - ±0.3 mm dá IoU de 87–95%;
  - ±0.7 mm dá 75–91%;
  - **±1 mm dá 64–87%, com média ~76%.**

  Com um traço de 2 mm, nem um método perfeito chegaria aos 100%.
- **Desvio sistemático:** o melhor deslocamento rígido da máscara tight sobre o GT é, em média, (−7.8, −8.2) px (≈ 1 mm), quase todo **na direção perpendicular às riscas**. Corrigir com o desvio médio aprendido nas outras formas (LOSO) dá IoU 68.0 → 69.9 e contorno 51.4 → 58.0.
- **Precisão do contorno por orientação da borda** (tight): borda perpendicular às riscas 63.2%, oblíqua 53.7%, paralela 38.9%.
- **As fotos de força não servem para afinar a segmentação.** Em `data/raw/force_pictures/`, a variação de fase é ≤ 0.2 rad, contra 3–10 rad nas fotos de formas, e o IoU contra a máscara do círculo de calibração é de 3–23%.

### 11.3 Primeiras alternativas (antes de haver modo de contacto)
| tentativa | resultado (média das 5) |
|---|---|
| Fundo polinomial (graus 1–3) | IoU 22–38%, falha |
| Fundo com o contacto excluído | melhor IoU 67.4% (LOSO 64.8%) |
| Nível de declive máximo | 30–43% |
| Cortes fixos de 45% / 55% / 65% | IoU 54.1 / 38.9 / 26.1 |
| Chan-Vese sobre a máscara tight | IoU 71.0, contorno 44.2 |

As variantes de largura de banda, corte, suavização e compensação da tabela 12.2 também são desta manhã, até à linha "suavização 0.004 + compensação α = 0.25".

### 11.4 O plano (09:42–09:58)
- **Decisões de partida:** só segmentação; o objetivo é melhorar a percentagem do contorno; contornos à mão, finos, em PNG. O supervisor quer o contorno melhorado precisamente nestas formas.
- **Métrica principal:** contorno a 1 mm, com a condição de o IoU não descer.
- **Tudo o que é novo entra num modo novo** (o modo de contacto). O default e o tight ficam iguais píxel a píxel, porque o pipeline de força usa o default com uma calibração própria (`CALIB_FOOTPRINT_SCALE = 1.874`).
- **Passos previstos:**
  1. ferramenta de avaliação;
  2. modo de contacto;
  3. contornos mais finos, desenhados por mim (passei este passo à frente às 16:59);
  4. fotos novas, para confirmar em dados não vistos.

---

## 12. Fase B: modo de contacto v2 (25 set; alterações a `detect_shape.py`)

### 12.1 Os três passos
São aplicados por cima do corte tight, só quando pedidos (`detect(..., **CONTACT_PARAMS)` ou `--contact`):
1. **Sinal mais nítido:** a suavização da fase passa de 0.008 para **0.004** da imagem.
2. **Encaixe da borda** (`refine_contour`):
   - um contorno ativo geodésico move cada borda para onde a fase varia mais depressa;
   - só atua numa faixa de um período das riscas (~27 px) à volta da borda;
   - usa σ = 0.0026 × 768 (≈ 2 px) e 20 iterações;
   - depois limpa manchas e buracos minúsculos (< 0.04% da imagem) e suaviza o contorno (σ ≈ 6 px).
3. **Compensação do deslocamento** (`compensate_displacement`):
   - calcula o deslocamento das riscas, `u = −Δφ·n/(2π|f|)`, com o fundo medido a 40 px da máscara e uma suavização de ~4 px;
   - puxa a máscara de volta **25%** desse deslocamento (`disp_alpha = 0.25`).

Parâmetros: `CONTACT_PARAMS = dict(tight=True, smooth_frac=0.004, refine=True, disp_alpha=0.25)`.

Linha de comandos nova: `--contact`, `--reference`, `--deformed` e `--stem`. O nome dos ficheiros de saída passou a vir da pasta e do ficheiro; antes estava fixo em `"star"`.

**Como foi aplicado:** o encaixe da borda foi testado às 10:21, antes de entrar no código. Apliquei as alterações por blocos (às 10:33 e das 15:37 às 15:54) e verifiquei-as no ficheiro: regressão 30/30, o Ring com 1 contacto e o buraco preservado, os Three Circles com 3 contactos.

### 12.2 Como cheguei a estes passos (fotos antigas, média das 5)
As linhas até "suavização 0.004 + compensação α = 0.25" são da manhã de 25 de setembro. O encaixe da borda foi testado às 10:21 e medido na ferramenta às 16:06. A suavização final do contorno entrou por volta das 17:00 (secção 13.4).

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

---

## 13. Fase C: avaliação, alternativas e validação (25 set, tarde; reunião a 29 set)

### 13.1 Primeiros números e pesquisa de parâmetros LOSO (15:58–16:11)
- **Primeiros números.** A ferramenta de avaliação (secção 10) correu pela primeira vez às 16:06. O modo de contacto já tinha os três passos, mas ainda não a suavização final do contorno (secção 13.4). Resultados (IoU / contorno 1 mm):
  - footprint 58.0 / 21.2;
  - tight 68.0 / 51.4;
  - **modo de contacto 70.7 / 67.1**.
- Às 16:11 corri os mesmos comandos no meu terminal e obtive os mesmos números.
- **Pesquisa LOSO** (lançada às 16:07). Testei 192 combinações: largura de banda {0.55, 0.7} × suavização {0.003, 0.004, 0.006, 0.008} × corte {0.30, 0.35, 0.40} × encaixe {não, sim} × compensação {0, 0.25, 0.5, 0.75}. Em cada ronda escolhi a combinação com melhor contorno, desde que o IoU não descesse.

| forma testada | IoU (tight → escolhido) | contorno 1 mm (tight → escolhido) |
|---|---|---|
| F | 61.9 → 61.8 | 50.5 → 66.8 |
| Ring | 69.6 → 73.5 | 44.3 → 67.3 |
| Square | 73.9 → 73.6 | 33.5 → 46.0 |
| Star | 70.7 → 61.2 | 69.0 → 68.0 |
| Three Circles | 63.7 → 52.5 | 59.6 → 51.3 |
| **média** | **68.0 → 64.5** | **51.4 → 59.9** |

- **O encaixe da borda e a compensação α = 0.25 foram escolhidos em todas as rondas.** Os outros três parâmetros mudaram de ronda para ronda, sinal de que afinar mais seria ajustar-se a estas 5 imagens.
- A melhor combinação usando as 5 formas (suavização 0.006) dá IoU 71.9% e contorno 67.7%, mas só dentro da amostra.

### 13.2 Figuras e onde está o erro que falta (16:14–16:27)
- **Figuras:** cada forma passou a ter três painéis de contorno (default antigo | tight antigo | novo), com o GT a branco.
- **Erro por orientação da borda** (medido nesta altura):

  | borda | tight antigo | novo |
  |---|---|---|
  | perpendicular às riscas | 63% | 79% |
  | oblíqua | 54% | 70% |
  | paralela às riscas | 39% | 67% |

  Nas bordas perpendiculares às riscas já se estava perto dos 80%. O que falta está nas bordas paralelas, onde o sensor só mede a fase uma vez por período das riscas (≈ 2.3 mm). Os casos mais visíveis são a perna esquerda do F e o "entalhe" no topo do Square.
- **17 variantes testadas sobre o modo de contacto**, sem mexer no código:

| tentativa | IoU / contorno 1 mm (média das 5) |
|---|---|
| Filtro *notch* da ondulação das riscas | 71.3 / 66.2 (contorno 0.5 mm: 38.2) |
| *Notch* + 40 iterações do encaixe | 71.6 / 68.1 (contorno 0.5 mm: 39.9) |
| Média num período ao longo da portadora | 71.5 / 63.4 |
| Suavizar a máscara (σ 3 / 6 px) | 70.8 / 67.4 e 71.0 / 67.3 |
| **Tirar o fundo da imagem antes da FTP** | **71.1 / 68.7** (+1.6; fica como opção) |

  Nenhuma se aproxima dos 80%.

### 13.3 A meta de 80% e as métricas (16:27–16:42)
- **Números nesta altura:**

| métrica | tight (Liam) | modo de contacto |
|---|---|---|
| Dice | 80.9 | **82.7** |
| contorno a 2 mm (≈ 1 período das riscas) | 81.5 | **84.5** |
| IoU | 68.0 | 70.7 |
| contorno a 1 mm | 51.4 | 67.1 |

- **Pelo que percebi, os 80% do supervisor referem-se à segmentação**, ou seja, a uma medida de sobreposição de áreas. As duas mais comuns são:
  - o Dice, a mais usada em artigos;
  - o IoU, mais exigente.

  Decidi mostrar as duas. O `summary.png` passou a ter três painéis: Dice | IoU | contorno a 1 mm.
- **Ainda falta** confirmar com o supervisor a que métrica se refere, sem escolher a que passa só porque passa. No Dice e no contorno a 2 mm, o método do Liam também já estava acima de 80%.
- **O que é o GT (16:42):** é o contorno vermelho desenhado à mão, a "resposta certa". 100% quer dizer que o contorno detetado fica exatamente em cima dele.

### 13.4 Suavização final: a versão final do modo de contacto (16:56–17:05)
Considerei CNN, interpolação, SAM 2, *data augmentation* e segmentação semântica. Com só 5 imagens com contorno, quase tudo o que é *deep learning* fica de fora. Passei à frente o desenho de contornos novos e fiz os outros passos por ordem: suavização final do contorno, classificador por píxel e CNN.

**Passo 1, suavização final do contorno.** Apliquei-a no `refine_contour`, e é a versão final do modo de contacto. Os resultados nas fotos antigas são estes:

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

- **Teste de Wilcoxon (5 fotos):**
  - o IoU melhora em 5/5 fotos (p = 0.0625, o mínimo possível com 5 pares);
  - o contorno melhora em 4/5 (+15.8 pontos, p = 0.125).
- **Consistência:** a variação do contorno entre formas caiu de ±12.2 para ±1.9 pontos.
- **Por orientação da borda** (versão final): perpendicular 77.7%, oblíqua 66.9%, paralela 64.9%, contra 63.2 / 53.7 / 38.9 do tight. A análise em fatias de 15° está na secção 14.1.
- **Regressão:** os modos default, tight e orientação+amplitude dão máscaras idênticas, píxel a píxel, às do código original (30 casos: 10 pares × 3 modos).
- **Pipeline de força:** no par de `final_images` dá 35.6 N e 2.72 mm de profundidade, sem alterações.

### 13.5 Classificador por píxel (Random Forest, LOSO; 17:02–17:05)
**Passo 2.** Treinei com 4 formas e testei na 5.ª, para cada forma.
- 18 variáveis por píxel:
  - o score, o score relativo ao pico e o score suavizado (4, 8 e 16 px);
  - o gradiente e a altura de fase;
  - o score a ±0.5 e ±1 período, ao longo da portadora e ao longo das riscas;
  - a distância às bordas do modo de contacto e do tight.
- 200 árvores, profundidade 14.

| forma testada | modo de contacto: Dice / IoU / contorno | Random Forest |
|---|---|---|
| F | 79.0 / 65.3 / 65.7 | 85.9 / 75.2 / 69.5 |
| Ring | 86.3 / 75.9 / 69.1 | 78.3 / 64.3 / 63.2 |
| Square | 87.5 / 77.8 / 64.9 | 89.1 / 80.3 / 51.8 |
| Star | 83.0 / 70.9 / 66.5 | 83.9 / 72.3 / 55.1 |
| Three Circles | 78.9 / 65.1 / 69.8 | 75.5 / 60.6 / 69.1 |
| **média** | **82.9 / 71.0 / 67.2** | 82.5 / 70.6 / 61.7 |

- **Em média, o Random Forest não compensa:** com 4 formas de treino, não generaliza.
- As variáveis mais importantes foram:
  - o score meio período ao lado, ao longo da portadora (0.18). Confirma, por outro caminho, o efeito do deslocamento das riscas;
  - a distância à borda do modo de contacto (0.17).
- Exigiu instalar o `scikit-learn 1.9.1` no `.venv`, que não está no `requirements.txt`.

### 13.6 CNN: posta de parte (17:05)
- Uma CNN treinada nas 5 fotos reais seria pior do que o Random Forest, porque tem muito mais parâmetros.
- Havia duas opções:
  - **A) CNN (U-Net) treinada com toques simulados.** Exigia instalar o PyTorch e horas de trabalho, e havia o risco de a rede aprender o simulador em vez da membrana real.
  - **B) Fotos novas primeiro** (idealmente ≥ 100 pares com contorno), e só depois Random Forest ou CNN.
- Escolhi a B, que é o caminho das secções 14 a 16.

### 13.7 Conclusão do dia (17:07)
Com estes dados, o método está perto do **máximo prático**:
- **afinar mais não generaliza:** o contorno dá 67% com parâmetros afinados nas 5 fotos e ~60% em formas não vistas;
- **outras variantes quase não ajudam:** testei ~20, e a melhor ganha 1–2 pontos, dentro do ruído de 5 imagens;
- **o Random Forest não melhora a média;**
- **o GT impõe um teto:** um desvio de 1 mm já dá ~76% de IoU, e o erro médio de borda é de 1.1 mm;
- **o sensor impõe outro limite:** só mede uma vez por período das riscas (2.3 mm), o que prejudica as bordas paralelas.

O que ainda pode mudar os números: um GT melhor, fotos novas e hardware (riscas mais finas ou em duas direções). **Decisão:** congelar o método e passar às fotos novas.

### 13.8 Problemas nas formas sem contorno (17:15–17:31)
- **P das fotos antigas:** o modo de contacto deixa uma mancha solta de ~170 px e conta 2 contactos.
  - A causa é a ordem dentro do `refine_contour`, que limpa as manchas **antes** de suavizar.
  - A correção (suavizar primeiro) foi testada: o P passa a 1 contacto e os números ficam iguais. **Ainda não está aplicada** (código na secção 24).
- **A barriga do P desaparece** no tight e no modo de contacto: foi pressionada com menos força e fica abaixo do corte.
- **No Square Circle** (2 contactos certos), o círculo do modo de contacto fica menos redondo do que o do tight.

### 13.9 Reunião com o supervisor (29 set)
- Preparei:
  - a explicação de todas as alterações;
  - uma página de resumo para mostrar na reunião (https://claude.ai/artifact/7VSEomPUFWABPYA3RjKq4r);
  - os comandos para correr tudo de raiz;
  - um resumo em pontos.
- Corri a avaliação no meu computador às 10:13 (`verification/eval_segmentation.csv` e `figures/segmentation/`).

---

## 14. Fase D: fotos novas com rotação (30 set a 6 out)

### 14.1 Planeamento (30 set)
- **Ideia:** tirar 6 fotos de cada forma, rodando a ponta de 60° em 60°.
- **60° ou 30°?** Para decidir, medi nas fotos antigas a precisão do contorno em função do ângulo entre a borda e as riscas:

| ângulo entre a borda e as riscas | contorno a 1 mm (modo de contacto) |
|---|---|
| 0–15° (paralela) | 63.4% |
| 15–30° | 68.6% |
| 30–45° | 68.7% |
| 45–60° | 65.3% |
| 60–75° | **81.0%** |
| 75–90° (perpendicular) | **76.4%** |

- **Há uma zona boa:** as bordas a menos de 30° da perpendicular dão 76–81%; fora dela fica tudo em 63–69%.
- **Com passos de 60°, cada borda cai na zona boa em exatamente uma das orientações,** porque 3 orientações a 60° cobrem os 180°. Com 30° cairia em duas: há mais redundância, mas a melhor vista de cada borda não melhora, e o número de contornos a desenhar duplicava (84 em vez de 42, para 7 formas).
- **Sugestão:** se houvesse tempo, repetir cada ângulo duas vezes em vez de passar a 30°.
- Estes números vêm só de 5 fotos, por isso são indicativos.

### 14.2 Recolha (5 out) e importação (6 out, 16:55–17:02)
- 8 formas (F, P, M, Ring, Square, Square Circle, Star, Three Circles) × 6 ângulos (0°, 60°, …, 300°) = 48 fotos, mais uma referência.
- **Horários:** a referência às 14:09:13 e as fotos das 14:09:32 às 14:38:50:

  | forma | F | P | Ring | Square | Square Circle | Three Circles | Star | M |
  |---|---|---|---|---|---|---|---|---|
  | hora | 14:09–14:11 | 14:12–14:14 | 14:14–14:16 | 14:19–14:20 | 14:21–14:23 | 14:27–14:28 | 14:34–14:36 | 14:37–14:38 |

- As fotos estavam na Secretária, numa pasta por forma (`F_shape_data`, `P_shape_data`, …), com a referência `reference_pic`.
- **Câmara diferente da do Liam:** 2520×1680 px, ~450 KB por foto, período das riscas ~51 px, ângulo da portadora −150°, **22 px/mm**.
- **Janela de análise ajustada** para manter 1 mm = 11.8 px na imagem de 768: `crop_ratio` = 0.432, calculado a partir do período.
- **A câmara mexeu-se** até ~16 px em relação à referência (por exemplo, o M a ~(+15, −6) px). Cada foto é alinhada com a referência antes da análise.
- **Os Three Circles a 240° e 300° eram o mesmo ficheiro,** idênticos byte a byte. Até ao conjunto v3, os Three Circles ficaram com 5 ângulos (47 fotos no total). Foi corrigido no conjunto v3 (secção 16.2).
- Pasta: `data/raw/shape_pictures_v2/<Forma>/rot_XXX.jpg` e `reference.jpg`.

### 14.3 Primeira segmentação (6 out, 17:13)
- **Rampa em vez de lomba.** Nas fotos antigas, a zona pressionada aparece na fase como uma lomba uniforme. Nas novas aparece como uma **rampa**, forte de um lado e cada vez mais fraca para o outro. Acontece em todas as formas e ângulos, sempre na mesma direção (perpendicular às riscas).
- **O corte do modo de contacto (35% do pico) só guarda o lado forte.** Daí as meias-luas nos Three Circles, o F partido e o quadrado reduzido a uma tira.
- **Alternativas testadas:**
  - **o corte a 15% do pico ajuda:** o Ring passa a anel e a Star parece uma estrela;
  - o modo "dipolo" do código antigo não ajuda;
  - o default dá algo parecido com o corte a 15%, mas com halo.
- **Havia duas opções:** repetir as fotos com o setup antigo, ou adaptar o método à geometria nova.
- **Decisão (17:26):** como não tenho acesso ao setup antigo, usei estas fotos, com o ajuste de brilho/contraste pedido pelo supervisor.

### 14.4 Ajuste de brilho/contraste (6 out, 17:27–18:20; imagens antes/depois a 7 out)
`src/tactile/adjust_photos.py` faz três passos:
1. alinhamento com a referência, por correlação de fase nas faixas laterais do suporte;
2. correção da iluminação, dividindo a foto por uma versão muito desfocada dela própria (σ = 150 px);
3. esticamento do contraste entre os percentis 1 e 99, dentro da membrana. Há também uma opção CLAHE.

As fotos ajustadas foram segmentadas com `verification/segment_photos_v2.py` (17:51). Comparei as versões sem GT, com dois critérios: número certo de contactos e variação da área entre ângulos.

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

- **Com a configuração final** (janela automática 0.432, corte 15%), o resultado é **37/47 com e sem ajuste**. Uma foto melhora (F a 300°, de 2 para 1 contacto) e outra piora (Square a 0°, de 1 para 2).
- **Conclusão:** o ajuste deixa as formas visíveis a olho, mas não muda a segmentação. O método mede a posição das riscas, que não depende do brilho nem do contraste.
- **Regra das versões (17:57):** a partir daqui, qualquer alteração que mude resultados passa a ter um ficheiro novo (`_v2`, `_v3`), para não perder a progressão.
- **Imagens:**
  - com e sem ajuste, com os contactos certos a verde e os errados a laranja: `verification/compare_adjustment.py`, às 18:13–18:20;
  - antes/depois, com as 8 formas bem visíveis nas fotos ajustadas: `verification/show_adjusted.py`, a 7 out às 15:02.
- **Por forma** (ajustada, corte 15%):

  | forma | contactos certos | área média | CV da área |
  |---|---|---|---|
  | F | 5/6 | 525 mm² | 37% |
  | M | 4/6 | 665 mm² | 17% |
  | P | 4/6 | 524 mm² | 42% |
  | Ring | 6/6 | 615 mm² | 17% |
  | Square | 5/6 | 455 mm² | 21% |
  | Square Circle | 5/6 | 704 mm² | 5% |
  | Star | 3/6 | 564 mm² | 32% |
  | Three Circles | 5/5 | 344 mm² | 35% |

### 14.5 A diferença física do sinal (6 out, 18:22–18:34)
A deteção nas fotos novas ficou muito pior do que nas antigas. O algoritmo é o mesmo nos dois casos; a diferença está no sinal:
- **O sinal está invertido** (é negativo) e **não é uniforme**: a deformação é mais forte de um lado do contacto, sempre na mesma direção.
- **Razão entre o pico negativo e o positivo:** Three Circles 3.41, F a 300° 3.80, Square a 60° 2.40. Nas fotos antigas era 0.13.
- **Força do sinal** (pico do z-score): 13.2 / 17.4 / 10.7, contra 24.7 nos Three Circles antigos. Cerca de metade.
- O corte do modo de contacto (35% do pico) só guarda o lado forte, o que dá meias-luas e formas partidas.
- **Tentativa de correção:** comparar cada píxel com o pico da sua vizinhança, em vez do pico do contacto. **Piorou**: 26/47 (vizinhança de 1 cm, corte 35%), 8/47 (1 cm, 50%) e 10/47 (2 cm, 35%), contra 37/47.

### 14.6 Mensagem ao supervisor (6 out, 18:36–18:40)
Preparei três versões em inglês:
- uma longa;
- uma curta;
- uma curta que não atribui as diferenças à recolha.

---

## 15. Fase E: combinação dos 6 ângulos com o molde do Liam (6 out, 23:24–23:59)

- **Objetivo:** usar os vários ângulos para melhorar a deteção, como estava combinado com o supervisor.
- **Método** (`verification/fuse_angles.py`):
  1. segmentar cada ângulo;
  2. estimar o eixo de rotação pela média dos centros das 6 máscaras (com ângulos igualmente espaçados, os desvios cancelam-se) e afiná-lo pela concordância entre máscaras. O sentido de rotação estimado foi −1 em todas as formas;
  3. rodar cada máscara de volta a 0° e ficar com os píxeis vistos por **pelo menos k dos 6 ângulos**;
  4. para comparar com o contorno de cada foto, rodar a forma combinada para o ângulo dessa foto.
- **Concordância entre as máscaras rodadas** (IoU médio entre pares): 0.31–0.59.
- **Ainda não havia contornos nas fotos novas.** Por isso usei os contornos do Liam como molde, porque as pontas são as mesmas. O molde é colocado na melhor posição possível: pode rodar, mover-se, espelhar-se e variar ±10% de tamanho. A medida é o **IoU de forma** (em %), que compara a forma mas ignora a posição:

| forma | um ângulo (média) | k=1 | k=2 | k=3 | k=4 | k=5 | k=6 |
|---|---|---|---|---|---|---|---|
| F | 55.4 | 53.2 | 63.3 | 60.4 | 59.7 | 45.7 | 12.8 |
| Ring | 55.9 | 56.1 | 65.8 | 65.9 | 55.7 | 19.8 | 1.2 |
| Square | 62.5 | 65.1 | 77.2 | 75.7 | 59.6 | 42.8 | 9.6 |
| Star | 60.3 | 41.3 | 63.9 | 73.7 | 78.3 | 67.8 | 23.9 |
| Three Circles | 35.1 | 34.4 | 51.0 | 53.5 | 15.1 | 0.2 | — |
| **média** | **53.8** | 50.0 | 64.2 | **65.8** | 53.7 | 35.3 | 11.9 |

- **O melhor ponto foi k = 3** (pelo menos 3 dos 6 ângulos), e foi esse o valor usado daí em diante. Para comparação, o melhor ângulo isolado de cada forma dá, em média, 69.0% de IoU de forma.
- **Esta estimativa dava +12 pontos de IoU de forma** face a um ângulo sozinho (53.8 → 65.8). Nas figuras, a Star combinada já é claramente uma estrela, e o F recupera a haste e o braço de cima.
- **Limitação:** sem contornos nas fotos novas, este número é só uma estimativa, porque o molde ignora os erros de posição.
- **Decisão:** desenhar os 48 contornos, com uma linha vermelha à volta da forma em cada foto e um ficheiro `_gt` por foto.

---

## 16. Fase F: contornos nas fotos novas e avaliação completa (6–7 out)

### 16.1 Os meus contornos
- Desenhei os 48 contornos entre 6 de outubro (23:48) e 7 de outubro (09:32), com linhas vermelhas finas (1–2 px), gravadas como `*_gt.jpg`.
- Com a compressão JPG, a linha mistura-se com as riscas (cor B,G,R ≈ 96,100,157). Por isso **a linha é detetada como a diferença face à foto limpa**.
- O contorno do F a 0° tinha uma pequena abertura. É fechada automaticamente, ligando pontas a menos de 90 px (~4 mm).

### 16.2 Montagem do conjunto v3 (`verification/build_dataset_v3.py`, 7 out 09:38)
- Cada desenho é associado à foto sobre a qual foi feito, comparando píxeis.
- **Three Circles:** os ângulos seguem os nomes dos desenhos. A foto que estava como 0° é a de 60°, a de 60° é a de 120°, e assim por diante até 300°.
- **A foto nova dos Three Circles a 0°** só existia com o desenho por cima. A versão limpa foi reconstruída preenchendo a linha a partir dos vizinhos (*inpainting*). Assim o conjunto passou a ter as 48 fotos.
- Pastas: fotos em `data/raw/shape_pictures_v3/`, contornos em `data/annotations/shape_pictures_v3/`.
- **Áreas dos contornos**, coerentes entre ângulos (1–5% de variação na maioria das formas):

  | forma | área |
  |---|---|
  | F | 375–411 mm² |
  | M | 489–552 mm² |
  | P | 409–458 mm² (buraco 64–72) |
  | Ring | 529–592 mm² (buraco 369–381) |
  | Square | 478–539 mm² |
  | Square Circle | 566–577 mm² (2 peças) |
  | Star | 160–212 mm² |
  | Three Circles | 232–239 mm² (3 peças) |

### 16.3 Resultados nas 48 fotos (`verification/eval_photos_v3.py`, 7 out 09:40–09:46)
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
- **O corte a 15% nas fotos antigas** dá Dice 79.9 ± 9.5, IoU 67.4 ± 12.0 e contorno 55.8 ± 9.1. É pior do que o corte a 35% (82.9 / 71.0 / 67.2), por isso **o melhor corte depende da câmara**.

### 16.4 A combinação, avaliada com os meus contornos
- **Este é o número válido:** **+2.4 pontos de Dice** (69.0 contra 66.7%, p = 0.13) e +2.5 de IoU (54.1 contra 51.6%, p = 0.16), sem significado estatístico. A estimativa com o molde (+12 de IoU de forma, secção 15) era otimista, porque ignorava a posição.
- **Efeito por forma:**
  - ajuda no F, P, Square, Ring e M;
  - piora no Square Circle e nos Three Circles;
  - o contorno a 1 mm piora 4.5 pontos.
- **Porque é que ajuda:** cada foto perde sempre o mesmo lado da imagem. Como a ponta roda, esse lado corresponde a partes diferentes do objeto. Combinar preenche o que cada foto perdeu e remove manchas que só uma foto vê.
- **Porque é que piora nas formas com peças separadas:** um pequeno erro no centro de rotação desloca cada peça.

### 16.5 Esclarecimentos (7 out, 09:49–10:00)
- **O Dice de 82.9% continua certo:** é o das fotos antigas (80.9% com o tight do Liam). As fotos novas são outro conjunto, com outra câmara e os meus contornos.
- **Tabela de todos os métodos** (09:51–09:54): `verification/compare_methods_table.py`; está na secção 18.
- **O que é "o corte":** primeiro o método encontra a zona deformada. Depois, em cada contacto, guarda os píxeis acima de uma fração do pico desse contacto: 35% no tight do Liam e no modo de contacto, 15% na versão para as minhas fotos. Um corte mais baixo apanha mais da forma, mas também mais halo.
- **Como se compara com o Liam:**
  - o método do Liam também correu nas minhas fotos, com o mesmo ajuste e a mesma janela;
  - a combinação de ângulos só existe nas minhas fotos, porque o Liam só tem uma foto por forma. Por isso, a comparação dos ângulos é feita só nas minhas fotos.

---

## 17. Fase G: setup melhorado (8 out, 15:56–16:26)

### 17.1 Referência nova (15:57–16:00)
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
- **Não melhorou o contraste das riscas,** que continua em metade do do Liam. Possíveis causas: luz difusa a chegar à lente, foco ou compressão da câmara.

### 17.2 Toque 1 no Square e o mapa de variação do período (16:04–16:14)
- **Toque 1** (referência `1.jpg` a 2520×1680 e foto `3.jpg` a 2176×1452, reduzida ao enviar):
  - pico do sinal 9.5 (sinal oposto 7.2), contra 8.6 no Square de 5 de outubro e 13.7 no do Liam;
  - corte 35%: 2 peças; corte 15%: 1 peça (~700 mm²).
- Nesta altura, uma medição rápida indicou que o zoom tinha mudado ~3.5% entre a referência e a foto. **Estava errada** (correção na secção 17.3).
- **Descoberta: a variação do período das riscas.** Calculei a **derivada da fase na direção perpendicular às riscas**. É a variação local do período, a mesma grandeza que o pipeline de força do Liam usa.
  - **Nas minhas fotos** (5 de outubro e setup melhorado), **a forma aparece inteira como um interior uniforme** (azul), com uma faixa forte (vermelha) num dos lados. F, P, anel, estrela, círculos e quadrado são todos reconhecíveis.
  - **Nas fotos do Liam,** a mesma derivada só mostra as bordas: azul de um lado e vermelho do outro.
- **Força do sinal** (pico dominante / oposto):

  | setup | dominante / oposto | razão |
  |---|---|---|
  | setup melhorado | 11.1 / 5.2 | 0.47 |
  | 5 de outubro | 30.0 / 15.1 | 0.50 |
  | Liam | 24.5 / 23.9 | 0.98 |

- **Interpretação:**
  - no setup do Liam, a pressão desloca as riscas de forma uniforme, o que dá um planalto na fase;
  - no meu, a pressão muda o período dentro da zona pressionada, o que, integrado, dá uma rampa na fase.

  Isto depende da **geometria da câmara** (o ângulo e a distância a que vê a membrana), não da qualidade da foto.
- **Primeiras tentativas de segmentar com este sinal,** em 6 fotos de 5 de outubro com contorno (Square 0°, F 0°, Ring 0°, Three Circles 60°, Star 0°, P 0°):
  - **preencher a "moldura" vermelha:** dá 0%, porque a moldura não é fechada;
  - **cortar o interior azul:** a melhor média é **59.6%** de Dice (corte 0.2, σ 6 px), contra **64.8%** do corte a 15% nas mesmas fotos. As máscaras ficam esburacadas por riscas finas na direção das riscas da membrana. Por foto (corte 15% entre parênteses):

    | Square | F | Ring | Three Circles | Star | P |
    |---|---|---|---|---|---|
    | 63.5 (59.2) | 66.8 (69.9) | 62.3 (80.1) | 51.5 (52.7) | 46.7 (52.2) | 66.6 (74.5) |

  - **Ainda não supera o método atual, mas é a pista principal** para o meu setup.
- Estas análises e figuras estão no scratchpad e ainda não estão no projeto.

### 17.3 Toque 2 e ajuste de brilho/contraste (16:20–16:24)
- **Toque 2** (referência `4.jpg` e foto `5.jpg`, ambas a 2176×1452):
  - alinhamento exato (ECC): escala +0.23% e deslocamento (−0.9, −5.8) px;
  - as duas referências (`4.jpg` e `1.jpg`) coincidem a +0.01%.
- **Correção:** o zoom **não** mudou 3.4–3.5% entre a referência e a foto pressionada. O alinhamento exato mostra uma diferença de 0.2% nos dois toques. O erro vinha da medição rápida do período, que é pouco precisa e é influenciada pelo contacto. As conclusões sobre o tipo de sinal mantêm-se.
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

### 17.4 Porque é que melhorar o setup não mudou o resultado (16:26)
- **O que melhorei** (luz, exposição, enquadramento) muda a aparência da foto.
- **O que limita a deteção** é o tipo de sinal: planalto no setup do Liam, rampa no meu. Isso depende da geometria da câmara, não da qualidade da foto.
- **A informação está lá:** no mapa de variação do período, as formas aparecem inteiras em todas as minhas fotos. O problema passou a ser do algoritmo, não do setup.
- **Proposta:**
  1. parar de mexer no setup;
  2. desenvolver a segmentação pela variação do período como versão nova (v3), sem mexer na atual, e testá-la nas 48 fotos anotadas, contra os 66.7% de Dice atuais;
  3. mostrar ao supervisor o que já existe: 82.9% de Dice nas fotos do Liam; +12 pontos nas minhas, com p = 2×10⁻⁷; a explicação física; a pergunta sobre a métrica dos 80%;
  4. fazer uma recolha nova com o setup melhorado só se o passo 2 funcionar.
- **Estado:** o passo 2 ainda não foi começado.

---

## 18. Tabela final da segmentação (para a tese)

Ficheiro: `results/segmentation_v2/method_comparison.png` (também `.csv` e `.md`).

| método | antigas: Dice | antigas: IoU | antigas: contorno 1 mm | novas: Dice | novas: IoU | novas: contorno 1 mm |
|---|---|---|---|---|---|---|
| Liam: default | 72.5 ± 11.3 | 58.0 ± 13.0 | 21.2 ± 10.1 | 61.9 ± 15.2 | 46.6 ± 15.9 | 23.0 ± 16.5 |
| Liam: tight | 80.9 ± 3.2 | 68.0 ± 4.5 | 51.4 ± 12.2 | 54.4 ± 17.7 | 39.5 ± 17.5 | 36.8 ± 17.0 |
| Modo de contacto (35%) | **82.9 ± 3.6** | **71.0 ± 5.2** | **67.2 ± 1.9** | 54.4 ± 19.2 | 39.7 ± 18.5 | **44.4 ± 17.7** |
| Modo de contacto, corte 15% | 79.9 ± 9.5 | 67.4 ± 12.0 | 55.8 ± 9.1 | 66.7 ± 13.9 | 51.6 ± 15.6 | 38.2 ± 20.6 |
| Corte 15% + 6 ângulos | — | — | — | **69.0 ± 13.0** | **54.1 ± 14.1** | 33.8 ± 12.1 |

- **Fotos antigas:** 5 fotos com os contornos do Liam; os parâmetros foram afinados nelas.
- **Fotos novas:** 48 fotos com os meus contornos. Só o corte a 15% foi escolhido nelas, e sem olhar para os contornos.
- **Meta de 80%:** em Dice, as fotos antigas já a passam (82.9%). Em IoU, nenhum conjunto chega lá.

---

# PARTE III: Fecho

## 19. Limitações

**Dados e audits**
1. **Os audits de força e formas medem a 3.ª harmónica.** As conclusões relativas mantêm-se, mas os períodos absolutos dos CSVs não são o período real (secção 7).
2. **A referência das fotos de força foi tirada em condições diferentes** (secção 3.5). O salto referência → 3 N não deve ser lido como resposta do sensor.
3. **O audit de temperatura usa 3 das 10 fotos** por temperatura. Como o ruído entre fotos é muito pequeno (desvio de L\* 0.01–0.05), isto não deve mudar as conclusões.
4. **O erro de temperatura aparente** divide por um declive que é quase zero na zona plana. Só é fiável na zona onde a pele responde.
5. **ΔE CIE76** exagera as diferenças em cores saturadas. Serve para comparar corridas entre si, não como valor absoluto.

**Segmentação**

6. **Contornos desenhados à mão:** o do Liam tem um traço de ~2 mm, e só um desvio de ±1 mm já dá ~76% de IoU. Os meus são mais finos, mas também são feitos a olho.
7. **Resolução na direção perpendicular às riscas:** é limitada pelo período (~2.3 mm). As bordas paralelas às riscas são as piores.
8. **O melhor corte depende da câmara:** 35% na do Liam, 15% na minha. Ainda não é escolhido automaticamente.
9. **Tipo de sinal no meu setup:** rampa em vez de planalto, com um sinal de ~metade do do Liam e um contraste das riscas de ~metade. Afeta todos os métodos, incluindo o do Liam (de 80.9% para 54.4% de Dice).
10. **Uma só referência** para os 30 minutos da recolha de 5 de outubro, com a câmara a mexer-se até 16 px.
11. **Poucas fotos com contorno:** 5 nas fotos antigas, 48 nas novas.
12. **As partes pressionadas com menos força são cortadas** (a barriga do P).
13. **A combinação de ângulos piora nas formas com peças separadas.**
14. **A Star é má em todos os métodos.**

---

## 20. Correções feitas durante o trabalho

Afirmações feitas durante a análise que depois se verificaram erradas. Ficam registadas para não irem parar à tese por engano:

| afirmação anterior | o que está certo | como foi verificado |
|---|---|---|
| O zoom muda 3.4–3.5% entre a referência e a foto pressionada | muda 0.2% | alinhamento exato (ECC) |
| A combinação de ângulos daria ~+12 pontos | os +12 eram de IoU de forma, sem contar a posição; com os meus contornos dá +2.4 de Dice e +2.5 de IoU, sem significado estatístico | avaliação com os 48 contornos novos |
| O ajuste de brilho/contraste melhora 2 a 4 fotos | 37/47 com e sem ajuste na configuração final | comparação lado a lado |
| A deteção do vermelho funciona nos contornos novos | a linha fina mistura-se com as riscas no JPG; passou a ser detetada pela diferença face à foto limpa | inspeção dos píxeis (B,G,R ≈ 96,100,157) |
| (audit) os 4.44% de variação entre formas vêm da câmara | vêm das fotos pressionadas; as referências variam 0.03% | valores por foto do `audit_shape.csv` |
| (audit) o contacto cobre ~49% da membrana | 8–20% (212–530 mm²) | contornos vermelhos, secção 6.5 |
| (audit) o período das riscas é ~25.2 px | ~75–77 px; 25.2 é a 3.ª harmónica | espetro sem a zona apagada |

---

## 21. Código

### 21.1 Trabalho anterior (audits, não alterado)
| ficheiro | linhas | o que faz |
|---|---|---|
| `verification/audit_images_V3.py` | 370 | audit das fotos de força |
| `verification/plot_force.py` | 249 | figuras e números da força |
| `verification/audit_shape.py` | 309 | audit das fotos de formas |
| `verification/audit_temperature.py` | 325 | audit da temperatura |
| `verification/.gitignore` | 2 | ignora `__pycache__/` e `*.pyc` |
| `requirements.txt` | 19 | ambiente fixado (commit `4341688`) |

### 21.2 `src/tactile/detect_shape.py` (alterado)
Cerca de 140 linhas alteradas, quase todas acrescentadas. O código completo das funções novas está no próprio ficheiro e no relatório de 8 de outubro (`docs/relatorio_segmentacao.md`, secção 6).
- **Imports:** `inverse_gaussian_gradient` e `morphological_geodesic_active_contour`, do `skimage.segmentation`.
- **Configuração:**
  - `STEM = None` (antes `"star"`);
  - `BW_FRAC = 0.55`, `GAC_SIGMA_FRAC = 0.0026`, `GAC_ITERS = 20`, `DISP_BG_MARGIN_FRAC = 0.052` e `DISP_SMOOTH_FRAC = 0.0052`;
  - `CONTACT_PARAMS`.
- **Funções novas:** `refine_contour(mask, score, roi, carrier, iters)` e `compensate_displacement(mask, dphi, carrier, roi, alpha)`.
- **`detect()`:** argumentos novos `bw_frac`, `smooth_frac`, `tight_lo_frac`, `refine` e `disp_alpha`, todos com os valores antigos por omissão. São passados à demodulação, à suavização e ao corte tight. No fim aplicam-se o encaixe da borda e a compensação.
- **Linha de comandos:** `--reference`, `--deformed`, `--stem` e `--contact`.
- **Regressão:** os modos do Liam dão máscaras idênticas às do original (30/30 casos), e o pipeline de força dá os mesmos 35.6 N / 2.72 mm.

### 21.3 Ficheiros novos
| ficheiro | linhas | o que faz |
|---|---|---|
| `src/tactile/detect_shape_liam_original.py` | 391 | cópia exata do original do Liam |
| `src/tactile/adjust_photos.py` | 106 | alinhamento + ajuste de brilho/contraste |
| `verification/eval_segmentation.py` | 514 | avaliação nas fotos antigas (+ `--search` LOSO) |
| `verification/segment_photos_v2.py` | 132 | segmentação das fotos rodadas sem contorno |
| `verification/compare_adjustment.py` | 141 | segmentação com e sem ajuste, lado a lado |
| `verification/fuse_angles.py` | 244 | combinação de ângulos com o molde do Liam |
| `verification/build_dataset_v3.py` | 81 | montagem do conjunto anotado v3 |
| `verification/eval_photos_v3.py` | 274 | avaliação das 48 fotos com os contornos + combinação |
| `verification/compare_methods_table.py` | 177 | tabela de todos os métodos |
| `verification/show_adjusted.py` | 92 | imagens antes/depois do ajuste |
| `docs/relatorio_segmentacao.md` | 345 | relatório de 8 de outubro |
| `docs/relatorio_segmentacao_v2.md` | 521 | relatório de 15 de outubro (segmentação) |
| `docs/relatorio_completo.md` | 1399 | este relatório |

---

## 22. Dados, resultados e figuras

### 22.1 Dados
| pasta | conteúdo | tamanho |
|---|---|---|
| `data/raw/force_pictures/` | 85 fotos de força (Liam) | 119 MB |
| `data/raw/full_color_experiment/` | 700 fotos de temperatura, pele a cores (Liam) | 489 MB |
| `data/raw/black_and_color_experiment/` | 700 fotos de temperatura, pele preto e cor (Liam) | 708 MB |
| `data/raw/final_images/` | par usado no teste do pipeline de força | 2.9 MB |
| `data/raw/shape_pictures/` | fotos antigas de formas (Liam, inalteradas) | 30 MB |
| `data/raw/shape_pictures_v2/` | 48 fotos de 5 de outubro + referência, tal como recolhidas | 22 MB |
| `data/raw/shape_pictures_v3/` | as mesmas, com os Three Circles corrigidos e a foto de 0° reconstruída | 22 MB |
| `data/annotations/shape_pictures_v3/` | os 48 contornos desenhados por mim | 27 MB |
| `data/processed/csv_files/` | calibração da força do Liam | 0.9 MB |
| `data/processed/shape_pictures_v2/` e `_v3/` | fotos alinhadas e ajustadas (geradas pelo script; não guardar no git) | 106 MB cada |

### 22.2 Resultados dos audits (Parte I)
| ficheiro | conteúdo |
|---|---|
| `verification/audit_force.csv` | 85 linhas, 13 colunas: métricas de cada foto de força |
| `verification/audit_shape.csv` | 15 linhas: métricas de cada foto de formas |
| `verification/audit_temp_full_color_experiment.csv` | 210 linhas: cor de cada foto, pele a cores |
| `verification/audit_temp_black_and_color_experiment.csv` | 210 linhas: cor de cada foto, pele preto e cor |
| `verification/debug_mask.png` | verificação visual do disco usado nos audits |
| `figures/force_*.png` | 4 figuras de força (secção 4.5) |
| `figures/temp_*.png` | 4 figuras de temperatura (secção 5.6) |

### 22.3 Resultados da segmentação (Parte II)
| pasta | conteúdo |
|---|---|
| `results/segmentation_v2/shape_pictures/` | fotos antigas: `eval_segmentation.csv`, uma figura por forma e o resumo |
| `results/segmentation_v2/shape_pictures_v2/` | fotos novas sem contorno: `segment_photos_v2.csv`, figuras, `brightness_contrast/` (9) e `fusion/` (9) |
| `results/segmentation_v2/shape_pictures_v3/` | fotos novas com contorno: `eval_photos_v3.csv`, `figures/` (8) e `before_after/` (9) |
| `results/segmentation_v2/method_comparison.*` | tabela de todos os métodos (`.png`, `.csv`, `.md`) |
| `figures/segmentation/` e `figures/shape_pictures_v2/` | primeiras versões das figuras (29 set e 6 out), guardadas |
| `verification/eval_segmentation.csv` e `segment_photos_v2.csv` | primeiras versões dos CSVs, guardadas |

### 22.4 Outras pastas
| pasta | conteúdo |
|---|---|
| `results/images_report/` | figuras originais do Liam |
| `results/midterm_slides/` | material dos slides intercalares (12 out), 18 imagens |
| `output/temp_shape_recon/` | saída do pipeline integrado (14 set) |

### 22.5 Figuras recomendadas para o relatório
**Parte I:**
- `figures/force_period_vs_load.png`: período contra força e saturação;
- `figures/force_noise.png`: onde o sinal entra no ruído;
- `figures/force_linearity.png`: erro do modelo linear;
- `figures/temp_full_color_experiment_sensitivity.png` e `figures/temp_black_and_color_experiment_sensitivity.png`: onde cada pele responde;
- `figures/temp_black_and_color_experiment_curves.png`: aquecimento contra arrefecimento (histerese).

**Parte II:**
- `results/segmentation_v2/method_comparison.png`: todos os métodos;
- `results/segmentation_v2/shape_pictures/figures/summary.png` e `Square_img_02.png`: fotos antigas;
- `results/segmentation_v2/shape_pictures_v3/before_after/overview.png`: o ajuste de brilho/contraste;
- `results/segmentation_v2/shape_pictures_v3/figures/F_shape.png`: fotos novas, uma foto sozinha e a combinação;
- `results/segmentation_v2/shape_pictures_v2/fusion/Star.png`: como funciona a combinação.

---

## 23. Como reproduzir

```bash
cd ~/master_thesis
source .venv/bin/activate
```

**Parte I: audits.** Grava numa pasta nova, para não escrever por cima dos resultados de setembro:
```bash
mkdir -p results/audits_rerun
python verification/audit_images_V3.py data/raw/force_pictures --out results/audits_rerun/audit_force.csv --quiet
python verification/plot_force.py --audit results/audits_rerun/audit_force.csv --outdir results/audits_rerun      # só depois de corrigir k = 4
python verification/audit_shape.py data/raw/shape_pictures --out results/audits_rerun/audit_shape.csv --force-csv results/audits_rerun/audit_force.csv
python verification/audit_temperature.py data/raw/full_color_experiment --out results/audits_rerun/audit_temp_full_color_experiment.csv --outdir results/audits_rerun
python verification/audit_temperature.py data/raw/black_and_color_experiment --out results/audits_rerun/audit_temp_black_and_color_experiment.csv --outdir results/audits_rerun
```

**Parte II: segmentação.**
```bash
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

## 24. Pendentes (com o código das correções)

### 24.1 Ordem no `refine_contour` (`src/tactile/detect_shape.py`, linhas 181–194)
Suavizar antes de limpar. Tira a mancha do P e não muda os números.

**Antes:**
```python
    out = mask.copy()
    out[band] = snapped[band]
    # the snap can leave pixel-sized specks or pinholes in the band; drop them
    floor = MIN_COMP_ABS * out.size
    for val in (1, 0):
        n_c, c_lab, c_stats, _ = cv2.connectedComponentsWithStats(
            (out == val).astype(np.uint8))
        for j in range(1, n_c):
                        if c_stats[j, cv2.CC_STAT_AREA] < floor:
                            out[c_lab == j] = 1 - val
    # the snap follows the fringes a little; smooth it like the final mask
    sm = cv2.GaussianBlur(out.astype(np.float32), (0, 0),
                          max(FINAL_SMOOTH_FRAC * n, 1.5))
    return (sm > 0.5).astype(np.uint8)
```

**Depois:**
```python
    out = mask.copy()
    out[band] = snapped[band]
    # the snap follows the fringes a little; smooth it like the final mask
    sm = cv2.GaussianBlur(out.astype(np.float32), (0, 0),
                          max(FINAL_SMOOTH_FRAC * n, 1.5))
    out = (sm > 0.5).astype(np.uint8)
    # drop pixel-sized specks and pinholes the snap and smoothing leave behind
    floor = MIN_COMP_ABS * out.size
    for val in (1, 0):
        n_c, c_lab, c_stats, _ = cv2.connectedComponentsWithStats(
            (out == val).astype(np.uint8))
        for j in range(1, n_c):
            if c_stats[j, cv2.CC_STAT_AREA] < floor:
                out[c_lab == j] = 1 - val
    return out
```

### 24.2 `plot_force.py`, linha 87
**Antes:**
```python
    k = 4. # k = 4 is arbitrary, chosen by me to make the departure visible. It's a visual aid, not for a fitted model.
```
**Depois:**
```python
    k = 4  # k = 4 is arbitrary, chosen by me to make the departure visible. It's a visual aid, not for a fitted model.
```

### 24.3 `audit_temperature.py`, linha 312
A linha tem de ficar dentro do `for`, com 8 espaços em vez de 4.

**Antes:**
```python
        # essentially zero above 33 degrees for the full-colour skin.
    ax.plot(mid, dL, marker="o", ms=3, lw=1.2, label=run)
```
**Depois:**
```python
        # essentially zero above 33 degrees for the full-colour skin.
        ax.plot(mid, dL, marker="o", ms=3, lw=1.2, label=run)
```

### 24.4 Outros pendentes
1. **Guardar no git:** repor o `.gitignore`, que está apagado no working tree (excluir `.venv/`, `.DS_Store`, `output/` e `data/processed/*`), e fazer o commit.
2. **Confirmar com o supervisor** se os 80% são em Dice (já atingidos nas fotos antigas) ou em IoU.
3. **Desenvolver a segmentação pela variação do período** para o meu setup, como versão nova, e testá-la nas 48 fotos anotadas.
4. **Escolher o corte automaticamente** consoante o setup.
5. **Melhorar a combinação nas formas com várias peças,** alinhando cada peça separadamente.
6. **Força:** trocar o modelo linear por um curvo (por exemplo quadrático) e repetir a referência na mesma sessão das fotos com carga.
7. **Temperatura:** decidir como tratar a histerese (calibração separada para aquecer e para arrefecer, ou incerteza declarada).
8. **Audits:** se se quiser o período real, reduzir a zona apagada no espetro (`dc_r`), para a fundamental (~75 px) deixar de ficar escondida.
9. **Próximas recolhas:**
   - uma referência imediatamente antes de cada toque;
   - a mesma resolução e zoom em todas as fotos;
   - toques a direito, com força constante e pausa entre toques.

   Para subir o contraste: tapar a luz direta dos LEDs à lente, usar foco e exposição manuais e a resolução máxima.

---

## 25. Notas

- **Página de resumo da reunião de 29 de setembro:** https://claude.ai/artifact/7VSEomPUFWABPYA3RjKq4r. Cobre só as fotos antigas.
- **Regra de versões:** nenhum ficheiro ou resultado anterior foi apagado ou alterado. Cada mudança que altera resultados tem uma versão nova (`_v2`, `_v3`). Este relatório é um ficheiro novo, e os relatórios v1 e v2 ficam como estavam.
- **Os números da Parte I foram confirmados a 15 de outubro,** voltando a correr os scripts. As figuras de força refeitas com `k = 4` são iguais às guardadas.
