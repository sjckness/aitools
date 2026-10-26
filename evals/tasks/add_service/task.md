In `battery_node.py` il nodo `BatteryNode` raccoglie le tensioni dal topic
`battery/voltage` ma non espone nulla. Aggiungi un servizio
`battery/get_status` (via `create_service`) che restituisce un dict:
`{"count": <letture ricevute>, "last": <ultima tensione o None>,
"low": <True se last < 11.0, False altrimenti; False se non ci sono letture>}`.
Aggiungi anche un servizio `battery/reset` che azzera le letture e restituisce
`{"ok": True}`. Fai passare `python3 -m unittest discover -s tests` (aggiungi
un test per `reset`).
