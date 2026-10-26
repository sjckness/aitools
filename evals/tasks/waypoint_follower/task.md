Completa il modulo `follower` in tre parti indipendenti (oggi stub):
1. `messages.py`: `Waypoint(x, y)` e `Path(waypoints)` (dataclass, `waypoints`
   lista di `Waypoint`). `Path.length()` = somma delle distanze euclidee fra
   waypoint consecutivi (0.0 se meno di 2). `Path.from_dict({"waypoints":
   [{"x":..,"y":..}, ...]})` e `Path.to_dict()` con round-trip identico.
2. `follower_node.py`: `FollowerNode(bus, tolerance=0.1)` si iscrive a `path`
   (dict Path) e a `odom` (dict con x, y). Ad ogni `odom`, se c'e' un
   waypoint corrente, pubblica su `cmd_vel` `{"linear": 1.0, "angular": 0.0}`;
   se la distanza dal waypoint corrente e' <= tolerance, passa al successivo
   (senza pubblicare per quel messaggio); finiti i waypoint pubblica
   `{"linear": 0.0, "angular": 0.0}` una sola volta. Un nuovo `path` riparte
   dal primo waypoint. Servizio `follower/status`: `{"index": i,
   "remaining": n, "done": bool}` (`done` True solo dopo aver ricevuto un
   path e averlo completato).
3. `tests/test_integration.py`: test di integrazione con path di 2 waypoint,
   simulando messaggi `odom`, che verifica la sequenza dei `cmd_vel` e lo
   stato finale `done`.
Fai passare `python3 -m unittest discover -s tests`.
