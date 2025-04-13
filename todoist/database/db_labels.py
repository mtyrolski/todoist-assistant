import json
from subprocess import DEVNULL, PIPE, run
from todoist.utils import COLOR_NAME_TO_TODOIST_CODE, get_api_key
from loguru import logger


class DatabaseLabels:
    def __init__(self):
        self._labels: list[dict] = []
        self._mapping_label_name_to_color: dict[str, str] = {}

    def reset(self):
        self._fetch_label_data()
        
    def fetch_label_colors(self) -> dict[str, str]:
        """
        Returns a dictionary mapping label names to their colors.
        """
        if not self._labels:
            self._fetch_label_data()
        
        mapping_name_to_color_code = {}
        for label in self._labels:
            label_name = label['name']
            color_name = label['color']
            if color_name in COLOR_NAME_TO_TODOIST_CODE:
                mapping_name_to_color_code[label_name] = COLOR_NAME_TO_TODOIST_CODE[color_name]
            else:
                logger.warning(f"Label color '{color_name}' not recognized.")
        return mapping_name_to_color_code

    def _fetch_label_data(self) -> None:
        """
        Fetches label data from the Todoist API and populates local attributes.
        """
        url = "https://api.todoist.com/rest/v2/labels"
        headers = {
            "Authorization": f"Bearer {get_api_key()}"
        }

        cmds = [
            "curl", url, "-H", f"Authorization: {headers['Authorization']}"
        ]

        response = run(cmds, stdout=PIPE, stderr=DEVNULL, check=True)

        if response.returncode != 0:
            logger.error("Error fetching labels from Todoist.")
            return

        try:
            labels = json.loads(response.stdout)
            self._labels = labels
            self._mapping_label_name_to_color = {
                label['name']: label['color'] for label in labels
            }
            logger.info(f"Fetched {len(labels)} labels.")
        except json.JSONDecodeError:
            logger.error("Failed to decode label data from Todoist API.")