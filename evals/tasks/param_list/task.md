Il parser in `params.py` non supporta le liste inline (`[1, 2.5, abc]`):
oggi restituisce la stringa grezza. Aggiungi il supporto in `parse_value`:
una lista inline diventa una `list` di valori parsati ricorsivamente con le
stesse regole degli scalari; `[]` e' la lista vuota. Fai passare
`python3 -m unittest discover -s tests`.
