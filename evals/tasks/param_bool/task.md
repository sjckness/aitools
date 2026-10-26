Il parser di parametri in `params.py` (stile `ros__parameters`, scritto a mano)
restituisce stringhe per i booleani e lascia le virgolette nelle stringhe
quotate. Correggi `parse_value` in modo che:
- `true` / `false` (case-insensitive) diventino `True` / `False`;
- `"abc"` e `'abc'` diventino `abc` (senza virgolette);
- numeri e il resto continuino a funzionare come prima.
Fai passare `python3 -m unittest discover -s tests`.
