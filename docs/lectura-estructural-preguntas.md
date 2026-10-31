# Diego's spot-check list (accumulated during E0 close-out, 2026-10-30)

Questions only the office can answer. Until answered, the engine shows each as a visible supuesto or duda, never a silent pick.

## From the spec (§12), still open
- Castillo stirrup sizes K-2…K-3A and K-4A's longitudinal (workbook vs drawing); K-5 section (drawing 20×30 on every sheet, workbook 20×40); K-15A.1/K-15A.2 in the workbook vs `K-15A` (6#8+6#6) in the drawing; C-3 (workbook 8 × 1", drawing 8#8+4#6).
- The «1/4"» weight: 0.384 vs 0.248 kg/m.
- Dados cover: 7.5 cm (workbook) vs 5 cm (drawing notes).
- #8 bars: the bar table lists laps, note 4 says weld from #8 — ask Marina's calculista.
- Marina's natural ground level (excavation stays a supuesto otherwise).

## Added in E0 close-out
- **D-X** (Marina ES-000, E2EC4 drawn inside D-4): a pedestal on D-4 or a separate dado? Today neither counted twice nor priced (Task 15b, R264).
- **D-3A height**: its corte writes «100» but draws it as long as D-3B's «120». The engine takes the text (R262).
- **PRUEBA-1 storey reading**: the engine reads each N.P.T. as the level of the slab the planta draws (PB 3.45, PA 3.15, azotea 1.20), because the azotea draws no slab and PB/PA do (R270). Confirm.
- **PRUEBA-1 azotea**: 10 of the 22 azotea castillos sit inside the planta alta perimeter and the section draws a slab band below +7.80 (6A41). Is the azotea a parapet or a partial roof slab?
- **Castillos through the slab**: are castillos measured through the 20 cm slab (today yes, ≈ 0.59 m³ on PRUEBA-1 EST-001) or to its underside, like the walls now are (R271)?
- **Dala de remate**: block walls are measured to the underside of the slab, not to the underside of the dala de remate; the dala is priced separately (E2). Confirm the office does not deduct it from the wall area, or does.
- **Wall length convention**: block-wall m² measured along the block core's centreline, each T-joint once (R275). Does the office measure along the axis, an exterior face, or something else?
- **PRUEBA-1 wall thickness**: the 18 cm outlines include a 15 mm aplanado band; the notes say 15 cm block, and the engine takes 15 (R275). Confirm.

## Added by the Marina transcription (Task 16, 2026-10-30)
The hand transcription (`evals/transcripcion/marina_lote_04_estructural.json`, 175 readings) has no `dudas`: every stack-family mark could be decided from the drawing. These are the places where the drawing itself is out of order, for Diego to confirm:
- **P-5's armado is written over P-4's stack** (ES-000, MTEXT 33AF5 «4#8 + 12#6 / 3E#3 VER CORTE», 0.43 m from P-4's title; nothing under P-5). The transcription gives it to P-5: P-4 already has «REFUERZO 12#6» / «2E#3 VER CORTE» and 12 bars in its corte; P-5's corte draws 16 bars (4 + 12). Confirm P-5 = 4#8+12#6, 3E#3.
- **K-10 in the castillo block** (ES-000/100/200/300): its title sits to the left of its 15×85 section with its stack under the title; on ES-400 the same K-10 is drawn the usual way. Confirm K-10 = 15×85, 6#6+4#4, 2E+1G#3 EXT@10 CENTRO@15.
- **CR-2** (ES-200/300/400): its bars are written as two callouts, «2#3» (top) and «2#4» (bottom), not as one line. The transcription reads 2#3+2#4 with E#2@15, 20×20. Confirm.
- **D-X** is titled «DADO» in its own cuadro (ES-000, 45×45, 8#6, 2E#3@10) but drawn like a column section; same question as above (pedestal or dado).
- **K-0 / K-X «CASTILLO AHOGADO»**: the drawn 40×15 and 40×20 are the block, not the castillo; 1#3 / 1#4 with no stirrup. Confirm they are priced as one bar in the block cell.
