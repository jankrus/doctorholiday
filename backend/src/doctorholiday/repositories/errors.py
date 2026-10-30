"""Domain errors raised by repositories when the database rejects a write."""


class DataConflictError(Exception):
    """A write broke a uniqueness or exclusion rule; the API answers 409."""


class EmailAlreadyRegisteredError(DataConflictError):
    pass


class TimeAlreadyBookedError(DataConflictError):
    """The doctor already has a booked appointment overlapping this time (BR-09)."""
