from tqdm import tqdm
from todoist.utils import TODOIST_COLOR_NAME_TO_RGB
from loguru import logger

from todoist.api import RequestSpec, TodoistAPIClient, TodoistEndpoints
from todoist.api.client import EndpointCallResult


class DatabaseLabels:
    def __init__(self):
        super().__init__()
        self._api_client = TodoistAPIClient()
        self._labels: list[dict] = []
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

    def _fetch_label_data(self) -> None:
        """
        Fetches label data from the Todoist API and populates local attributes.
        """
        spec = RequestSpec(endpoint=TodoistEndpoints.LIST_LABELS, rate_limited=True)
        labels = self._api_client.request_json(spec, operation_name="list labels")
        if not isinstance(labels, list):
            logger.error("Unexpected payload returned when fetching labels")
            return

        self._labels = labels
        self._mapping_label_name_to_color = {label['name']: label['color'] for label in labels}
        logger.info(f"Fetched {len(labels)} labels.")

    def anonymize_sub_db(self, project_mapping: dict[str, str], label_mapping: dict[str, str]):
        if not self._labels:
            logger.debug("Labels not fetched yet. Fetching now.")
            self._fetch_label_data()

        for ori_name, anonym_name in tqdm(label_mapping.items(), desc="Anonymizing labels", unit="label"):
            logger.info(f"Anonymizing label '{ori_name}' to '{anonym_name}'")
            self._mapping_label_name_to_color[anonym_name] = self._mapping_label_name_to_color[ori_name]

            local_label = next((label for label in self._labels if label['name'] == ori_name), None)
            if local_label:
                local_label['name'] = anonym_name
            else:
                logger.warning(f"Label '{ori_name}' not found in local data.")

        logger.info(f"Anonymized {len(label_mapping)} labels.")
        logger.debug(f"Label mapping: {self._mapping_label_name_to_color}")
