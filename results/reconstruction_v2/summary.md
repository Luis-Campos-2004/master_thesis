# Reconstrução 3D: Liam (v1) contra v2

## Fotos de força (círculo de 314 mm², 32 fotos de teste: img_04-05 de cada nível)

| | Liam (v1) | v2 |
|---|---|---|
| erro médio da força (N) | 10.35 | 2.02 |
| RMSE da força (N) | 12.54 | 2.39 |
| erro máximo da força (N) | 28.9 | 4.6 |
| viés da força (N) | -10.35 | -0.91 |
| erro médio da profundidade (mm) | 0.722 | 0.054 |
| RMSE da profundidade (mm) | 0.873 | 0.072 |
| erro máximo da profundidade (mm) | 1.88 | 0.16 |
| área mediana da região (mm², real 314) | 379 | 313 |
| Dice mediano contra o círculo (%) | 23.8% | 92.5% |
| fotos com 1 só contacto | 0 | 31 |
| fotos com força 0 | 2 | 0 |
| fotos sem toque com contacto falso (de 4) | 4 | 0 |

Validação da calibração v2 (deixando um nível de força de fora, 48 fotos de calibração): erro médio da força 1.55 N, da profundidade 0.049 mm.

## Fotos de formas: contorno da superfície 3D contra o contorno desenhado

| forma | Liam (v1): Dice / IoU / contorno 1 mm | v2: Dice / IoU / contorno 1 mm |
|---|---|---|
| F shape | 69.1 / 52.7 / 10.1 | 79.0 / 65.3 / 65.7 |
| Ring | 82.3 / 69.9 / 34.8 | 86.3 / 75.9 / 69.1 |
| Square | 81.9 / 69.3 / 26.1 | 87.5 / 77.8 / 64.9 |
| Star | 76.2 / 61.6 / 21.1 | 83.0 / 70.9 / 66.5 |
| Three Circles | 52.2 / 35.3 / 9.2 | 78.9 / 65.1 / 69.8 |
| **média** | **72.3 / 57.8 / 20.3** | **82.9 / 71.0 / 67.2** |

## Fotos de formas: força e profundidade (sem valor real conhecido)

| forma | foto | método | contacto | área (mm²) | força (N) | profundidade (mm) | fora da calibração |
|---|---|---|---|---|---|---|---|
| F shape | img_02.jpg | v1 | 1 | 461 | 100.9 | 5.52 | sim |
| F shape | img_02.jpg | v2 | 1 | 416 | 6.8 | 0.37 |  |
| F shape | img_03.jpg | v1 | 1 | 464 | 140.7 | 7.18 | sim |
| F shape | img_03.jpg | v2 | 1 | 416 | 7.3 | 0.79 |  |
| P shape | img_02.jpg | v1 | 1 | 262 | 106.2 | 5.74 | sim |
| P shape | img_02.jpg | v2 | 1 | 211 | 14.6 | 1.89 |  |
| Ring | img_02.jpg | v1 | 1 | 397 | 61.6 | 3.88 | sim |
| Ring | img_02.jpg | v2 | 1 | 592 | ≥ 92.7 | ≥ 3.43 | sim |
| Square | img_02.jpg | v1 | 1 | 362 | 39.5 | 2.92 |  |
| Square | img_02.jpg | v2 | 1 | 468 | 43.7 | 2.34 |  |
| Square Circle | img_02.jpg | v1 | 1 | 254 | 29.4 | 2.37 |  |
| Square Circle | img_02.jpg | v1 | 2 | 211 | 39.1 | 2.90 |  |
| Square Circle | img_02.jpg | v2 | 1 | 353 | 43.5 | 2.86 |  |
| Square Circle | img_02.jpg | v2 | 2 | 268 | ≥ 41.9 | ≥ 3.43 | sim |
| Star | img_02.jpg | v1 | 1 | 340 | 113.1 | 6.03 | sim |
| Star | img_02.jpg | v2 | 1 | 303 | ≥ 47.5 | ≥ 3.43 | sim |
| Three Circles | img_02.jpg | v1 | 1 | 109 | 38.0 | 2.84 |  |
| Three Circles | img_02.jpg | v1 | 2 | 101 | 40.0 | 2.94 |  |
| Three Circles | img_02.jpg | v1 | 3 | 111 | 49.1 | 3.37 | sim |
| Three Circles | img_02.jpg | v2 | 1 | 127 | ≥ 19.9 | ≥ 3.43 | sim |
| Three Circles | img_02.jpg | v2 | 2 | 93 | ≥ 14.5 | ≥ 3.43 | sim |
| Three Circles | img_02.jpg | v2 | 3 | 69 | ≥ 10.9 | ≥ 3.43 | sim |
