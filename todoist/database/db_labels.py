from typing import TypedDict

from tqdm import tqdm
from todoist.utils import TODOIST_COLOR_NAME_TO_RGB
from loguru import logger

from todoist.api import RequestSpec, TodoistAPIClient, TodoistEndpoints
from todoist.api.client import EndpointCallResult


class LabelRecord(TypedDict):
    name: str
    color: str


class DatabaseLabels:
    def __init__(self):
        super().__init__()
        self._api_client = TodoistAPIClient()
        self._labels: list[LabelRecord] = []
        self._mapping_label_name_to_color: dict[str, str] = {}
        self._fetch_label_data()

    def reset(self):
        self._fetch_label_data()

    @property
    def last_call_details(self) -> EndpointCallResult | None:
        """Expose metadata about the most recent API call."""

        return self._api_client.last_call_result

    def fetch_label_colors(self) -> dict[str, str]:
        """
        Returns a dictionary mapping label names to their colors.
        """
        mapping_name_to_color_code = {}

        for label_name, color in self._mapping_label_name_to_color.items():
            if color in TODOIST_COLOR_NAME_TO_RGB:
                mapping_name_to_color_code[label_name] = TODOIST_COLOR_NAME_TO_RGB[color]
            else:
                logger.warning(f"Label color '{color}' not recognized.")

        return mapping_name_to_color_code

    def list_labels(self) -> list[LabelRecord]:
        """Return a shallow copy of fetched label records."""

        return [{"name": label["name"], "color": label["color"]} for label in self._labels]

    def _fetch_label_data(self) -> None:
        """
        Fetches label data from the Todoist API and populates local attributes.
        """
        labels = self._fetch_all_labels()

        self._labels = labels
        self._mapping_label_name_to_color = {label["name"]: label["color"] for label in labels}
        logger.info(f"Fetched {len(labels)} labels.")

    def _fetch_all_labels(self) -> list[LabelRecord]:
        labels: list[LabelRecord] = []
        cursor: str | None = None

        while True:
            params: dict[str, str | int] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            spec = RequestSpec(
                endpoint=TodoistEndpoints.LIST_LABELS,
                params=params,
                rate_limited=True,
            )
            payload = self._api_client.request_json(spec, operation_name="list labels")
            page_labels, next_cursor = self._extract_label_results_page(
                payload, operation_name="list labels"
            )
            labels.extend(page_labels)
            if not next_cursor:
                break
            cursor = next_cursor

        return labels

    @staticmethod
    def _extract_label_results_page(
        payload: object, *, operation_name: str
    ) -> tuple[list[LabelRecord], str | None]:
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected payload type returned from {operation_name}: {type(payload).__name__}")

        results = payload.get("results")
        if not isinstance(results, list):
            raise RuntimeError(f"Unexpected results payload returned from {operation_name}")

        typed_results: list[LabelRecord] = []
        for item in results:
            if not isinstance(item, dict):
                raise RuntimeError(f"Unexpected non-object label record in {operation_name} response")
            name = item.get("name")
            color = item.get("color")
            if not isinstance(name, str) or not isinstance(color, str):
                raise RuntimeError(f"Unexpected label shape returned from {operation_name}")
            typed_results.append({"name": name, "color": color})
        next_cursor = payload.get("next_cursor")
        return typed_results, str(next_cursor) if isinstance(next_cursor, str) else None

    def anonymize_sub_db(self, project_mapping: dict[str, str], label_mapping: dict[str, str]):
        if not self._labels:
            logger.debug("Labels not fetched yet. Fetching now.")
            self._fetch_label_data()

        for ori_name, anonym_name in tqdm(label_mapping.items(), desc="Anonymizing labels", unit="label"):
            self._mapping_label_name_to_color[anonym_name] = self._mapping_label_name_to_color[ori_name]

            local_label = next((label for label in self._labels if label["name"] == ori_name), None)
            if local_label:
                local_label["name"] = anonym_name
            else:
                logger.warning(f"Label '{ori_name}' not found in local data.")

        logger.info(f"Anonymized {len(label_mapping)} labels.")
        logger.debug(f"Label mapping: {self._mapping_label_name_to_color}")
