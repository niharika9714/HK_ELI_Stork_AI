"""Read identity established by trusted server-side SSO middleware."""

from collections.abc import Mapping


def resolve_user(request):
    # Server-side middleware must populate this after validating SSO.
    # Never populate it directly from browser headers or request JSON.
    identity = request.environ.get("hkeli.verified_identity")

    if not isinstance(identity, Mapping):
        raise PermissionError(
            "Corporate authentication is required. "
            "Verified SSO identity was not provided."
        )

    required = (
        "id",
        "country",
        "line_of_business",
        "tableau_username",
    )

    user = {}
    for field in required:
        value = identity.get(field)
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 320
            or any(ord(char) < 32 for char in value)
        ):
            raise PermissionError(
                f"Verified identity has a missing or invalid {field}."
            )
        user[field] = value.strip()

    # Match the application's entitlement registry conventions.
    user["country"] = user["country"].upper()
    user["line_of_business"] = user["line_of_business"].lower()

    return user