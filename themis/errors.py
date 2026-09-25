"""The one exception type whose message is written for the person who sent the
input, so the API may show it verbatim. It names only things the caller
supplied (a column, a table, a mapping role). Every other exception is an
internal failure: the API logs it and answers with a generic message instead
of echoing implementation detail (paths, SQL, library text).

Subclasses ValueError so existing `except ValueError` callers are unaffected."""


class InputError(ValueError):
    pass


class RowLimitError(InputError):
    """The input has more logical rows than the service is configured to hold in memory."""
