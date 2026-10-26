"""Parser minimale di file di parametri in stile ROS 2 (`ros__parameters`)."""


def parse_value(s):
    s = s.strip()
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def parse_params(text):
    root = {}
    stack = [(-1, root)]
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key, _, val = line.strip().partition(":")
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if val.strip() == "":
            child = {}
            parent[key.strip()] = child
            stack.append((indent, child))
        else:
            parent[key.strip()] = parse_value(val)
    return root
