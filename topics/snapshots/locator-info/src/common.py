from construct import Container


def warn_bad_data(msg: str) -> None:
    """Informative wrapper to be used when warning about an encounter with nonfatal bad data"""
    print(f"WARN: {msg}. Therefore some or all of the data might be partial and its integrity cannot be guaranteed")


class CustomException(Exception):
    """A general exception used to identify an exception that was explicitly raised from within the script.

    Useful to determine if the exception message is informative enough to be displayed as a lone error message before exiting with an error code,
    or is it an unexpected error that better be raised normally.
    """

    def __init__(self, message):
        super().__init__(f"ERROR: {message}")


def enforce(condition: bool, message: str):
    """Validator that raises CustomException. Created to mimic the convenience of the one lined assert"""
    if not condition:
        raise CustomException(message)


StowVersionType = int
RawDataContainerType = Container
