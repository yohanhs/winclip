# Fuentes incluidas

Solo se distribuyen fuentes con licencia libre **SIL Open Font License 1.1**. Cada familia
conserva su `OFL.txt`, descargado del repositorio oficial [google/fonts](https://github.com/google/fonts).

| Familia | Pesos incluidos | Uso previsto |
|---|---|---|
| Montserrat | Bold, ExtraBold, Black | Preset principal tipo Hormozi |
| Poppins | Bold, ExtraBold, Black | Alternativa geométrica |
| Anton | Regular | Títulos de impacto |
| Bebas Neue | Regular | Condensada para hooks |
| League Spartan | Bold, Black | Estilo MrBeast |
| Inter | Regular, SemiBold, Bold | Texto y UI |

## Fuentes comerciales

Gotham y otras fuentes comerciales **no se incluyen**. Se cargan en local desde
`USER_FONTS_DIR` (por defecto `~/Library/Fonts`) y nunca se commitean al repo público.

## Regenerar

```bash
python3 scripts/download_fonts.py
```
