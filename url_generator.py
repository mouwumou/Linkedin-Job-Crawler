from dataclasses import dataclass, field
import itertools
import re
import urllib.parse
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class FilterSelection:
    """Represents a chosen label/value pair for a filter."""

    label: str
    value: Optional[str]


@dataclass
class FilterDefinition:
    """Static configuration describing an individual filter dimension."""

    param_key: str
    choices: Dict[str, Optional[str]]
    default_labels: Optional[Sequence[str]] = None
    enabled_by_default: bool = True


@dataclass
class QueryPlan:
    """Final representation for one combination of filters and query params."""

    params: Dict[str, str]
    labels: Dict[str, str] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return BASE_URL + urllib.parse.urlencode(self.params)


def _normalize_location_entry(entry: Any) -> Tuple[Optional[str], Dict[str, str]]:
    if isinstance(entry, dict):
        normalized = {k: v for k, v in entry.items() if v is not None}
        location_value = normalized.pop("location", None)
        return location_value, normalized
    return entry, {}


def _normalize_selection_input(
    value: Optional[Iterable[str] | str],
) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return list(value)


def _resolve_filter_config(
    include_filters: Optional[Iterable[str] | str | bool]
) -> Tuple[Dict[str, FilterDefinition], bool, bool]:
    definitions: Dict[str, FilterDefinition] = dict(DEFAULT_FILTER_DEFINITIONS)
    use_state_filter = False
    use_county_filter = False

    if include_filters:
        if include_filters is True:
            requested = list(FULL_FILTER_DEFINITIONS.keys()) + ["state_filter"]
        elif isinstance(include_filters, str):
            if include_filters.lower() == "all":
                requested = list(FULL_FILTER_DEFINITIONS.keys()) + ["state_filter"]
            else:
                requested = [include_filters]
        else:
            requested = list(include_filters)

        invalid: List[str] = []
        for name in requested:
            if name == "state_filter":
                use_state_filter = True
            elif name == "county_filter":
                use_county_filter = True
            elif name in FULL_FILTER_DEFINITIONS:
                definitions[name] = FULL_FILTER_DEFINITIONS[name]
            else:
                invalid.append(name)

        if invalid:
            available_filters = ", ".join(FULL_FILTER_DEFINITIONS.keys())
            raise KeyError(
                "Unknown filter identifier(s): "
                f"{', '.join(invalid)}. Available: {available_filters}, state_filter"
            )

    return definitions, use_state_filter, use_county_filter


class FilterOption:
    """Mutable state for a single filter dimension."""

    def __init__(self, name: str, definition: FilterDefinition):
        self.name = name
        self.definition = definition
        self.enabled: bool = definition.enabled_by_default
        self._selected_labels: Optional[List[str]] = None

    @property
    def selected_labels(self) -> List[str]:
        if self._selected_labels is not None:
            return list(self._selected_labels)
        if self.definition.default_labels is None:
            return list(self.definition.choices.keys())
        return list(self.definition.default_labels)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def select(self, labels: Optional[Iterable[str]]) -> None:
        if labels is None:
            self._selected_labels = None
            return
        if isinstance(labels, str):
            normalized = [labels]
        else:
            normalized = list(labels)
        for label in normalized:
            if label not in self.definition.choices:
                available = ", ".join(self.definition.choices.keys())
                raise KeyError(
                    f"Unknown label '{label}' for filter '{self.name}'. Available: {available}"
                )
        self._selected_labels = normalized

    def active_selections(self) -> List[FilterSelection]:
        if not self.enabled:
            return []
        selections = []
        for label in self.selected_labels:
            value = self.definition.choices[label]
            selections.append(FilterSelection(label=label, value=value))
        return selections

    def snapshot(self) -> Dict[str, object]:
        return {
            "enabled": self.enabled,
            "selected": self.selected_labels if self.enabled else [],
            "available": list(self.definition.choices.keys()),
        }


class FilterOptions:
    """Manages multiple job-search filter dimensions with defaults and overrides."""

    def __init__(
        self,
        definitions: Dict[str, FilterDefinition],
        overrides: Optional[Dict[str, Dict[str, object]]] = None,
    ) -> None:
        self._options: Dict[str, FilterOption] = {
            name: FilterOption(name, definition)
            for name, definition in definitions.items()
        }
        if overrides:
            self.apply(overrides)

    def apply(self, overrides: Dict[str, Dict[str, object]]) -> None:
        for name, config in overrides.items():
            if name not in self._options:
                available = ", ".join(self._options.keys())
                raise KeyError(
                    f"Unknown filter '{name}'. Available filters: {available}"
                )
            option = self._options[name]
            if "enabled" in config:
                option.set_enabled(bool(config["enabled"]))
            if "values" in config:
                raw_values = config["values"]
                if raw_values is None:
                    option.select(None)
                elif isinstance(raw_values, str):
                    option.select([raw_values])
                elif isinstance(raw_values, Iterable) and all(isinstance(v, str) for v in raw_values):
                    option.select(list(raw_values))
                else:
                    raise TypeError("Filter values must be a string or iterable of strings.")

    def set(
        self,
        name: str,
        *,
        enabled: Optional[bool] = None,
        values: Optional[Iterable[str]] = None,
    ) -> None:
        option = self._get(name)
        if enabled is not None:
            option.set_enabled(enabled)
        if values is not None:
            option.select(values)

    def _get(self, name: str) -> FilterOption:
        if name not in self._options:
            available = ", ".join(self._options.keys())
            raise KeyError(f"Unknown filter '{name}'. Available filters: {available}")
        return self._options[name]

    def summary(self) -> Dict[str, Dict[str, object]]:
        return {name: option.snapshot() for name, option in self._options.items()}

    def iter_plans(
        self, base_params: Optional[Dict[str, str]] = None
    ) -> Iterator[QueryPlan]:
        base_params = dict(base_params or {})
        active_dimensions = []
        for name, option in self._options.items():
            selections = option.active_selections()
            if not selections:
                continue
            active_dimensions.append((name, option.definition.param_key, selections))

        if not active_dimensions:
            yield QueryPlan(params=base_params.copy(), labels={})
            return

        product_args = [
            [(name, param_key, selection) for selection in selections]
            for name, param_key, selections in active_dimensions
        ]

        for combination in itertools.product(*product_args):
            params = base_params.copy()
            labels: Dict[str, str] = {}
            for name, param_key, selection in combination:
                if selection.value is not None:
                    params[param_key] = selection.value
                labels[name] = selection.label
            yield QueryPlan(params=params, labels=labels)


BASE_URL = "https://www.linkedin.com/jobs/search/?"

DEFAULT_KEYWORD = "data center"

DEFAULT_STATIC_PARAMS = {
    "sortBy": "R",
}

DEFAULT_FILTER_DEFINITIONS: Dict[str, FilterDefinition] = {

}

FULL_FILTER_DEFINITIONS: Dict[str, FilterDefinition] = {
    "experience_levels": FilterDefinition(
        param_key="f_E",
        choices={
            "Internship": "1",
            "Entry level": "2",
            "Associate": "3",
            "Mid-Senior": "4",
            "Director": "5",
            "Executive": "6",
        },
    ),
    "remote_types": FilterDefinition(
        param_key="f_WT",
        choices={"On-site": "1", "Hybrid": "2", "Remote": "3"},
    ),
    "date_posted": FilterDefinition(
        param_key="f_TPR",
        choices={"Any time": None, "Past week": "r604800", "Past month": "r2592000"},
    ),
    "salary_ranges": FilterDefinition(
        param_key="f_SB2",
        choices={
            "$40K+": "1",
            "$60K+": "2",
            "$80K+": "3",
            "$100K+": "4",
            "$120K+": "5",
        },
    ),
}

FULL_FILTER_ORDER = [
    "experience_levels",
    "remote_types",
    "date_posted",
    "salary_ranges",
]

def generate_urls(
    keyword: Optional[str] = DEFAULT_KEYWORD,
    *,
    states: Optional[Iterable[str] | str] = None,
    counties: Optional[Iterable[str] | str] = None,
    include_filters: Optional[Iterable[str] | str | bool] = False,
    filter_overrides: Optional[Dict[str, Dict[str, object]]] = None,
    base_params: Optional[Dict[str, str]] = None,
    include_summary: bool = False,
) -> List[str] | Dict[str, object]:
    """Generate LinkedIn job search URLs using the configured filter options.

    Parameters
    ----------
    keyword:
        Primary job keyword supplied by the user. Defaults to
        :data:`DEFAULT_KEYWORD`. Pass ``None`` or an empty string to omit the
        ``keywords`` query parameter entirely.
    states:
        State names recognised by :func:`state_filter`. Only applied when
        ``include_filters`` enables ``"state_filter"`` or when this argument is
        explicitly provided. ``None`` (default) expands to every configured
        state when the state filter is active. Provide an empty iterable to
        disable state-based filtering while still keeping the state filter entry
        in the summary.
    counties:
        Reserved for future support. Leave ``None`` or empty. Supplying values
        raises :class:`NotImplementedError` until :func:`county_filter` is
        implemented.
    include_filters:
        Choose which optional filters from :data:`FULL_FILTER_DEFINITIONS` to
        apply. Pass ``True`` or ``"all"`` to enable every available filter plus
        the state filter, or supply a collection of filter names (for example
        ``["experience_levels", "state_filter"]``). Falsy values keep the
        default of no extra filters.
    filter_overrides:
        Optional mapping of filter names to configuration dictionaries. Each
        configuration may contain a boolean ``enabled`` flag and a ``values``
        collection with the labels to keep for that filter.
    base_params:
        Extra query parameters to merge with :data:`DEFAULT_STATIC_PARAMS`.
    include_summary:
        When set to ``True`` the return value becomes a dictionary containing
        the generated :class:`QueryPlan` objects and a human-friendly summary of
        the active filters, including location selections.

    Returns
    -------
    List[str] | Dict[str, object]
        The generated URLs by default, or a dictionary with ``plans`` and
        ``summary`` when ``include_summary`` is ``True``.
    """
    (
        filter_definitions,
        state_filter_enabled,
        county_filter_enabled,
    ) = _resolve_filter_config(include_filters)
    filters = FilterOptions(filter_definitions, overrides=filter_overrides)
    params = dict(DEFAULT_STATIC_PARAMS)
    if base_params:
        params.update(base_params)
    if keyword:
        params["keywords"] = keyword

    plans = list(filters.iter_plans(params))

    cleaned_plans: List[QueryPlan] = []
    for plan in plans:
        cleaned_params = {k: v for k, v in plan.params.items() if v is not None}
        cleaned_plans.append(QueryPlan(params=cleaned_params, labels=dict(plan.labels)))

    state_filter_requested = state_filter_enabled or states is not None
    state_options: Dict[str, object] = {}
    available_states: List[str] = []
    state_selections: List[Tuple[str, object]] = []

    final_plans: List[QueryPlan] = cleaned_plans

    if state_filter_requested:
        state_options = state_filter()
        available_states = list(state_options.keys())

        normalized_states = _normalize_selection_input(states)
        if normalized_states is None:
            normalized_states = available_states

        for state in normalized_states:
            if state not in state_options:
                available = ", ".join(available_states)
                raise KeyError(
                    f"Unknown state '{state}'. Available states: {available}"
                )
            state_selections.append((state, state_options[state]))

        if state_selections:
            updated_plans: List[QueryPlan] = []
            for plan in cleaned_plans:
                for state_label, state_value in state_selections:
                    location_value, extra_params = _normalize_location_entry(
                        state_value
                    )
                    new_params = dict(plan.params)
                    if location_value:
                        new_params["location"] = location_value
                    for key, value in extra_params.items():
                        new_params[key] = value
                    new_labels = dict(plan.labels)
                    new_labels["state"] = state_label
                    updated_plans.append(
                        QueryPlan(params=new_params, labels=new_labels)
                    )
            final_plans = updated_plans

    if counties:
        raise NotImplementedError(
            "County filtering is not yet supported. Provide an empty value for 'counties'."
        )

    if county_filter_enabled:
        raise NotImplementedError(
            "County filtering is planned but not yet implemented."
        )

    if include_summary:
        summary = filters.summary()
        if not available_states:
            available_states = list(state_filter().keys())
        summary["state_filter"] = {
            "enabled": bool(state_selections),
            "selected": [state for state, _ in state_selections],
            "available": available_states,
        }
        summary["county_filter"] = {
            "enabled": county_filter_enabled,
            "selected": [],
            "available": [],
        }
        return {
            "plans": final_plans,
            "summary": summary,
        }

    return [plan.url for plan in final_plans]


def extend_url_with_filter(url: str, include_filters: Iterable[str] | str | bool) -> List[str]:
    """Return new URLs composed by layering extra filters onto an existing URL.
    
    Parameters
    ----------
    url:
        Existing LinkedIn job search URL to extend.
    include_filters:
        Choose which optional filters from :data:`FULL_FILTER_DEFINITIONS` to include.  

    Returns
    -------
    List[str]
        A list of new URLs with the applied filters.
    """

    if not include_filters:
        return [url]

    parts = urllib.parse.urlsplit(url)
    base_query_pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    base_params: Dict[str, str] = {}
    for key, value in base_query_pairs:
        base_params[key] = value

    (
        filter_definitions,
        state_filter_enabled,
        county_filter_enabled,
    ) = _resolve_filter_config(include_filters)

    ordered_definitions: Dict[str, FilterDefinition] = {}
    for name in FULL_FILTER_ORDER:
        definition = filter_definitions.get(name)
        if definition and definition.param_key not in base_params:
            ordered_definitions[name] = definition
    for name, definition in filter_definitions.items():
        if definition.param_key not in base_params and name not in ordered_definitions:
            ordered_definitions[name] = definition

    if not ordered_definitions and not state_filter_enabled and not county_filter_enabled:
        return [url]

    filters = FilterOptions(ordered_definitions)
    plans = list(filters.iter_plans(base_params))

    cleaned_plans: List[QueryPlan] = []
    for plan in plans:
        cleaned_params = {k: v for k, v in plan.params.items() if v is not None}
        cleaned_plans.append(QueryPlan(params=cleaned_params, labels=dict(plan.labels)))

    final_plans: List[QueryPlan] = cleaned_plans

    if state_filter_enabled:
        state_options = state_filter()
        available_states = list(state_options.keys())
        state_selections: List[Tuple[str, object]] = []
        for state in available_states:
            state_selections.append((state, state_options[state]))

        if state_selections:
            updated_plans: List[QueryPlan] = []
            for plan in final_plans:
                for state_label, state_value in state_selections:
                    location_value, extra_params = _normalize_location_entry(state_value)
                    new_params = dict(plan.params)
                    if location_value:
                        new_params["location"] = location_value
                    for key, value in extra_params.items():
                        new_params[key] = value
                    new_labels = dict(plan.labels)
                    new_labels["state"] = state_label
                    updated_plans.append(QueryPlan(params=new_params, labels=new_labels))
            final_plans = updated_plans

    if county_filter_enabled:
        raise NotImplementedError(
            "County filtering is planned but not yet implemented."
        )

    final_urls: List[str] = []
    seen: set[str] = set()

    for plan in final_plans:
        new_query = urllib.parse.urlencode(plan.params, doseq=True)
        new_url = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
        )
        if new_url not in seen:
            seen.add(new_url)
            final_urls.append(new_url)

    if not final_urls:
        return [url]

    return final_urls


# def county_filter() -> dict:
#     pass


def state_filter() -> dict:
    STATE_LABELS = {
        "Alabama": "Alabama, United States",
        "Alaska": "Alaska, United States",
        "Arizona": "Arizona, United States",
        "Arkansas": "Arkansas, United States",
        "California": "California, United States",
        "Colorado": "Colorado, United States",
        "Connecticut": "Connecticut, United States",
        "Delaware": "Delaware, United States",
        "District of Columbia": "District of Columbia, United States",
        "Florida": "Florida, United States",
        "Georgia": "Georgia, United States",
        "Hawaii": "Hawaii, United States",
        "Idaho": "Idaho, United States",
        "Illinois": "Illinois, United States",
        "Indiana": "Indiana, United States",
        "Iowa": "Iowa, United States",
        "Kansas": "Kansas, United States",
        "Kentucky": "Kentucky, United States",
        "Louisiana": "Louisiana, United States",
        "Maine": "Maine, United States",
        "Maryland": "Maryland, United States",
        "Massachusetts": "Massachusetts, United States",
        "Michigan": "Michigan, United States",
        "Minnesota": "Minnesota, United States",
        "Mississippi": "Mississippi, United States",
        "Missouri": "Missouri, United States",
        "Montana": "Montana, United States",
        "Nebraska": "Nebraska, United States",
        "Nevada": "Nevada, United States",
        "New Hampshire": "New Hampshire, United States",
        "New Jersey": "New Jersey, United States",
        "New Mexico": "New Mexico, United States",
        "New York": "New York, United States",
        "North Carolina": "North Carolina, United States",
        "North Dakota": "North Dakota, United States",
        "Ohio": "Ohio, United States",
        "Oklahoma": "Oklahoma, United States",
        "Oregon": "Oregon, United States",
        "Pennsylvania": "Pennsylvania, United States",
        "Rhode Island": "Rhode Island, United States",
        "South Carolina": "South Carolina, United States",
        "South Dakota": "South Dakota, United States",
        "Tennessee": "Tennessee, United States",
        "Texas": "Texas, United States",
        "Utah": "Utah, United States",
        "Vermont": "Vermont, United States",
        "Virginia": "Virginia, United States",
        "Washington": "Washington, United States",
        "West Virginia": "West Virginia, United States",
        "Wisconsin": "Wisconsin, United States",
        "Wyoming": "Wyoming, United States",
    }
    return STATE_LABELS
