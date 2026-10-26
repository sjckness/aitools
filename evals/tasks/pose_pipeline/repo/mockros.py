"""Mini framework mock in stile ROS 2 (solo per le fixture)."""


class Bus:
    def __init__(self):
        self._subs = {}
        self._services = {}

    def publish(self, topic, msg):
        for cb in list(self._subs.get(topic, [])):
            cb(msg)

    def subscribe(self, topic, cb):
        self._subs.setdefault(topic, []).append(cb)

    def register_service(self, name, handler):
        self._services[name] = handler

    def call(self, name, request=None):
        if name not in self._services:
            raise KeyError("servizio sconosciuto: " + name)
        return self._services[name](request)


class Node:
    def __init__(self, name, bus):
        self.name = name
        self.bus = bus

    def create_subscription(self, topic, cb):
        self.bus.subscribe(topic, cb)

    def create_publisher(self, topic):
        return lambda msg: self.bus.publish(topic, msg)

    def create_service(self, name, handler):
        self.bus.register_service(name, handler)
