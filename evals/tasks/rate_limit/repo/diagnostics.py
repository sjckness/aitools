"""Statistiche di diagnostica (non usate da VelocityNode)."""


def moving_average(window):
    if not window:
        return 0.0
    return sum(window) / (len(window) + 1)
