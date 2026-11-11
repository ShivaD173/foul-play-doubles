"""Translate client preview constraints into the engine's indexed team options."""

from dataclasses import dataclass
from itertools import combinations, permutations


@dataclass
class TeamPreviewFilterSide:
    """Client-only constraints; this is not a class exported by poke_engine.

    Historical leads are recorded as a set, so either slot order is allowed.
    """

    valid_pokemon: list[str]
    leads: list[tuple[str, str]] | None = None


def team_preview_options(
    pokemon_names: list[str], constraints: TeamPreviewFilterSide
) -> list[tuple[int, int, int, int]]:
    """Return [lead A, lead B, backup, backup] using zero-based engine indices.

    Serializer order is the preview reserve order: the first two become active
    slots and the remaining four remain reserves. Backup order is immaterial
    to the engine, so avoid searching duplicate actions with reversed backups.
    """
    if len(pokemon_names) != 6 or len(set(pokemon_names)) != 6:
        raise ValueError("Team preview requires six distinct Pokemon")
    allowed = set(constraints.valid_pokemon)
    if not allowed.issubset(pokemon_names):
        raise ValueError("Preview constraints contain Pokemon absent from the team")
    allowed_indices = [i for i, name in enumerate(pokemon_names) if name in allowed]
    lead_pairs = (
        None
        if constraints.leads is None
        else {frozenset(pair) for pair in constraints.leads}
    )
    options = []
    for lead_a, lead_b in permutations(allowed_indices, 2):
        if (
            lead_pairs is not None
            and frozenset((pokemon_names[lead_a], pokemon_names[lead_b]))
            not in lead_pairs
        ):
            continue
        backups = [i for i in allowed_indices if i not in (lead_a, lead_b)]
        options.extend((lead_a, lead_b, a, b) for a, b in combinations(backups, 2))
    if not options:
        raise ValueError("Preview constraints leave no valid four-Pokemon teams")
    return options
