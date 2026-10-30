"""Data access layer: the only code that builds queries.

Each function takes the request's `Session` (doctorholiday.db.DbSession) and neither commits nor
rolls back; the request transaction does. Writes that can hit a constraint run in a SAVEPOINT and
raise a `DataConflictError` subclass, so a conflict leaves the outer transaction usable and the
database's error text never leaves this package.
"""
