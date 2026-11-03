# Test stub: only the names the checker imports. Version parsing is not used
# by the functions these tests call, so parse() fails loudly if reached.
class InvalidVersion(ValueError):
    pass


def parse(value):
    raise NotImplementedError("packaging stub: parse() is not part of these tests")
