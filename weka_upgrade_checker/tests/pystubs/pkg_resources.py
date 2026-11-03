# Test stub: makes the checker's "is packaging installed" probe succeed, so
# importing it in a test never runs `pip install` (no network in tests).
class DistributionNotFound(Exception):
    pass


def get_distribution(name):
    return name
