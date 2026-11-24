"""Default deny: the app only starts if every route declares who may call it (#16).

A route declares it by depending on one of the dependencies in `auth.dependencies`
(`require_roles`, `ActiveUser`, `CurrentSession`, `reject_session`, `public`). Each of them carries
its allowed roles; a route with several of them allows the intersection. `enforce_default_deny`
runs in `create_app`, and the tests compare `route_roles` with `x-roles` in `openapi.yaml`.
"""

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

from doctorholiday.auth.dependencies import AUTHZ_ATTRIBUTE


def _rules(dependant: Dependant) -> list[frozenset[str]]:
    found: list[frozenset[str]] = []
    roles = getattr(dependant.call, AUTHZ_ATTRIBUTE, None)
    if roles is not None:
        found.append(roles)
    for child in dependant.dependencies:
        found.extend(_rules(child))
    return found


def routes(app: FastAPI) -> Iterator[RouteContext]:
    """Every route with the prefix and dependencies of the routers it was included through."""
    yield from iter_route_contexts(app.routes)


def route_roles(route: RouteContext) -> frozenset[str] | None:
    """The roles that pass the route's authorization, or None if it declares no rule.

    Anything that is not an API route (a mounted app, a plain Starlette route) has no rule.
    """
    if not isinstance(route.original_route, APIRoute) or route.dependant is None:
        return None
    found = _rules(route.dependant)
    if not found:
        return None
    return frozenset.intersection(*found)


def routes_without_rule(app: FastAPI) -> list[str]:
    return [
        f"{','.join(sorted(route.methods or ()))} {route.path}"
        for route in routes(app)
        if route_roles(route) is None
    ]


def enforce_default_deny(app: FastAPI) -> None:
    missing = routes_without_rule(app)
    if missing:
        raise RuntimeError(f"routes without an authorization rule: {', '.join(missing)}")
