Completa la pipeline di odometria in tre parti indipendenti (oggi sono stub
che sollevano `NotImplementedError`):
1. `messages.py`: `Twist(linear, angular)` e `Pose2D(x, y, theta)` (dataclass)
   con `to_dict()` e `Pose2D.from_dict(d)` / `Twist.from_dict(d)`; il
   round-trip deve essere identico. `from_dict` solleva `ValueError` se manca
   una chiave.
2. `odom_node.py`: `OdomNode(bus, dt=0.1)` si iscrive a `cmd_vel` (dict
   Twist), integra la posa (x += v*cos(theta)*dt; y += v*sin(theta)*dt;
   theta += w*dt) e pubblica `Pose2D.to_dict()` su `odom` ad ogni messaggio.
   Servizio `odom/reset`: riporta la posa a zero e restituisce `{"ok": True}`.
3. `tests/test_integration.py`: aggiungi un test di integrazione che
   pubblica 10 messaggi `cmd_vel` con linear=1.0, angular=0 e verifica che
   l'ultima `odom` abbia x ~ 1.0 (assertAlmostEqual) e y == 0.
Fai passare `python3 -m unittest discover -s tests`.
