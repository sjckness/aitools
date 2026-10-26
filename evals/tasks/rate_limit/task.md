`VelocityNode` (`velocity_node.py`) riceve `{"linear": v, "angular": w}` su
`cmd_vel` e ripubblica su `cmd_vel_safe`, limitando solo `linear` a
`+-max_linear`. Aggiungi il limite anche per `angular` (parametro costruttore
`max_angular`, default 1.0, simmetrico) e un servizio `velocity/set_limits`
che accetta `{"max_linear": x, "max_angular": y}` (chiavi opzionali) e
restituisce i limiti correnti come dict con le stesse due chiavi.
Aggiungi test e fai passare `python3 -m unittest discover -s tests`.
