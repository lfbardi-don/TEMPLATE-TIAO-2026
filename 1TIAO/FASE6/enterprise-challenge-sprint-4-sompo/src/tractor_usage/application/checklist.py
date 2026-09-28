"""Preventive-inspection agenda derived from observed physical conditions.

The mapping from physical condition to inspected component is an engineering
hypothesis. It has not been validated by an insurance inspector; per-item
findings recorded on completed cases are the evidence that can confirm,
refine, or retire each item in a later version.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from tractor_usage.application.contracts import InspectionAgendaItem, InspectionEpisode


CHECKLIST_VERSION = "inspection-checklist-v1"
CHECKLIST_VALIDATION_STATUS = "engineering_hypothesis"


@dataclass(frozen=True)
class _ItemDefinition:
    id: str
    component: str
    check: str
    conditions: tuple[str, ...]


_DEFINITIONS = (
    _ItemDefinition(
        "engine",
        "Motor",
        "Ruído ou vibração anormal em carga, fixação dos coxins, vazamentos e fumaça no escapamento.",
        ("lugging", "overload_torque"),
    ),
    _ItemDefinition(
        "air_intake",
        "Admissão de ar",
        "Estado e restrição do filtro de ar e vedação das mangueiras de admissão.",
        ("overload_torque",),
    ),
    _ItemDefinition(
        "cooling",
        "Arrefecimento",
        "Nível e estado do líquido, limpeza da colmeia do radiador, correia e ventilador.",
        ("thermal_under_load", "overload_torque"),
    ),
    _ItemDefinition(
        "clutch_transmission",
        "Embreagem e transmissão",
        "Trepidação ou patinação da embreagem, ruído ou dificuldade de engate e aspecto do óleo da transmissão.",
        ("lugging", "harsh_torque_rise"),
    ),
    _ItemDefinition(
        "driveline_pto",
        "Cardã, TDP e acoplamentos",
        "Folga e desgaste nas cruzetas do cardã, no eixo da TDP e nos pinos de engate do implemento.",
        ("harsh_torque_rise",),
    ),
    _ItemDefinition(
        "tires_ballast",
        "Pneus e lastro",
        "Desgaste irregular e cortes nas garras, pressão dos pneus e lastro adequado ao implemento.",
        ("loaded_high_slip",),
    ),
    _ItemDefinition(
        "axles_front_drive",
        "Eixos e tração dianteira",
        "Ruído, folga e vazamentos nos eixos e no acionamento da tração dianteira.",
        ("loaded_high_slip",),
    ),
    _ItemDefinition(
        "operating_practice",
        "Prática de operação",
        "Com o gestor da frota, revisar marcha, rotação e lastro usados no trabalho em que os episódios ocorreram.",
        ("lugging", "loaded_high_slip"),
    ),
)


def build_inspection_agenda(
    episodes: Iterable[InspectionEpisode],
) -> tuple[InspectionAgendaItem, ...]:
    """Return only the items whose conditions were observed, in fixed order."""

    observed = tuple(episodes)
    items: list[InspectionAgendaItem] = []
    for definition in _DEFINITIONS:
        triggering = tuple(
            episode
            for episode in observed
            if set(episode.conditions) & set(definition.conditions)
        )
        if not triggering:
            continue
        matched = {
            condition for episode in triggering for condition in episode.conditions
        }
        items.append(
            InspectionAgendaItem(
                id=definition.id,
                component=definition.component,
                check=definition.check,
                conditions=tuple(
                    condition for condition in definition.conditions if condition in matched
                ),
                episode_ids=tuple(episode.id for episode in triggering),
            )
        )
    return tuple(items)


def agenda_storage(items: tuple[InspectionAgendaItem, ...]) -> dict[str, object]:
    return {
        "version": CHECKLIST_VERSION,
        "validation_status": CHECKLIST_VALIDATION_STATUS,
        "items": [
            {
                "id": item.id,
                "component": item.component,
                "check": item.check,
                "conditions": list(item.conditions),
                "episode_ids": list(item.episode_ids),
            }
            for item in items
        ],
    }
