import datetime as dt
from dataclasses import dataclass
from typing import Any

from loguru import logger
from pandas import DataFrame


@dataclass
class _ProjectEntry_API_V9:
    id: str
    name: str
    color: str
    parent_id: str | None
    child_order: int
    view_style: str
    is_favorite: bool
    is_archived: bool
    is_deleted: bool
    is_frozen: bool
    can_assign_tasks: bool
    shared: bool
    created_at: str
    updated_at: str
    v2_id: str
    v2_parent_id: str | None
    sync_id: str | None
    collapsed: bool
    inbox_project: bool = False
    description: str = ''
    default_order: int | None = None
    public_access: bool = False

    def __repr__(self):
        return f'Project {self.name}'

    def __str__(self):
        return f'Project {self.name}'


@dataclass
class _Event_API_V9:
    id: str
    object_type: str
    object_id: str
    event_type: str
    event_date: str
    parent_project_id: str | None
    parent_item_id: str | None
    initiator_id: str | None
    extra_data: dict[str, Any]
    extra_data_id: str | None
    v2_object_id: str | None
    v2_parent_item_id: str | None
    v2_parent_project_id: str | None

    def __repr__(self):
        return f'Event {self.object_type} {self.event_type}'

    def __str__(self):
        return f'Event {self.object_type} {self.event_type}'


@dataclass
class _Task_API_V9:
    id: str
    is_deleted: bool
    added_at: str
    child_order: int
    responsible_uid: str | None
    content: str
    description: str
    user_id: str
    assigned_by_uid: str
    project_id: str
    section_id: str
    sync_id: str | None
    collapsed: bool
    due: str | None | dict[str, Any]
    parent_id: str | None
    labels: list[str]
    checked: bool
    priority: int
    note_count: int
    added_by_uid: str
    completed_at: str | None
    deadline: str | None
    duration: dict[str, str | int] | None
    updated_at: str
    v2_id: str | None
    v2_parent_id: str | None
    v2_project_id: str | None
    v2_section_id: str | None
    day_order: str | None

    def __repr__(self):
        return f'Task {self.content}'

    def __str__(self):
        return f'Task {self.content}'

    @property
    def kwargs(self) -> dict[str, Any]:
        basic_kwargs = self.__dict__.copy()
        basic_kwargs['duration_unit'] = None if self.duration is None else self.duration.get('unit')
        basic_kwargs['duration'] = None if self.duration is None else self.duration.get('amount')
        return basic_kwargs

    @property
    def duration_kwargs(self) -> dict[str, str | int] | None:
        if self.duration is None:
            return None

        if any(not isinstance(self.duration, dict), 'duration' not in self.duration, 'unit' not in self.duration):
            return None

        return {'duration': self.duration['duration'], 'unit': self.duration['unit']}

    @property
    def due_datetime(self) -> dt.datetime | None:
        if self.due is None:
            return None
        date_str = self.due['date'] if isinstance(self.due, dict) else self.due

        try:
            return dt.datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            try:
                return dt.datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                return None


ProjectEntry = _ProjectEntry_API_V9
TaskEntry = _Task_API_V9
EventEntry = _Event_API_V9


@dataclass
class Task:
    id: str
    task_entry: TaskEntry

    def __eq__(self, other):
        return self.id == other.id


@dataclass
class Project:
    id: str
    project_entry: ProjectEntry
    tasks: list[Task]
    is_archived: bool

    def __eq__(self, other):
        return self.id == other.id
    


def is_event_rescheduled(event: 'Event') -> bool:
    """
    Check if the event is a reschedule event.
    
    ex. of resheduled event:
    'initiator_id': None,
    'extra_data': {'client': 'Mozilla/xxxx; Todoist/xxxx',
    'content': 'Invite people to conf',
    'due_date': '2025-04-06T21:59:59.000000Z',
    'last_due_date': '2025-04-05T21:59:59.000000Z',
    'note_count': 0},
    'extra_data_id': xxxxxx,
        
    """
    return all(
        [
            event.event_entry.event_type == 'updated',
            'due_date' in event.event_entry.extra_data,
            'last_due_date' in event.event_entry.extra_data,
        ]
    )

_EVENT_SUBTYPES_MAPPING = {
    'rescheduled': is_event_rescheduled,
}

@dataclass
class Event:
    event_entry: EventEntry
    id: str
    date: dt.datetime

    def __repr__(self):
        return f'Event {self.id} ({self.date}) {self.name}'

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    @property
    def name(self) -> str | None:
        if 'content' in self.event_entry.extra_data:
            return self.event_entry.extra_data['content']
        if 'name' in self.event_entry.extra_data:
            return self.event_entry.extra_data['name']
        return None
    
    @property
    def event_type(self) -> str:
        """
        Get the event type.
        
        For now basic types 'added', 'updated', 'completed', 'deleted' are supported
        and some subtypes are supported as well.
        For example, 'updated' is a basic type,
        but it is extended with 1 subtype 'rescheduled' (of 'updated').
        """
        matched_types = [event_type for event_type, is_match in _EVENT_SUBTYPES_MAPPING.items() if is_match(self)]
        if len(matched_types) > 0:
            assert len(matched_types) == 1, 'More than one event type matched'
            return matched_types[0]
        return self.event_entry.event_type


SUPPORTED_EVENT_TYPES = ['added', 'updated', 'completed', 'deleted']


def events_to_dataframe(
    activity: set[Event],
    project_id_to_name: dict[str, str],
    project_id_to_root: dict[str, Project],
) -> DataFrame:
    """
    Basing on list of events, it takes all of them and returns
    dataframe containing all SUPPORTED_EVENT_TYPES
    (all types are added, updated, completed, deleted, uncompleted,
    archived, left, unarchived, shared -- not all are supported)

    Events are sorted by date, from the oldest [0, 1, ...] to the newest [..., -2, -1]
    """

    # Sorting events by date
    events = sorted(activity, key=lambda event: event.date)

    # Creating dataframes
    mapping_data: dict[str, list] = {
        'id': [],
        'title': [],
        'date': [],
        'type': [],
        'parent_project_id': [],
        'parent_project_name': [],
        'root_project_id': [],
        'root_project_name': [],
        'parent_item_id': [],
    }
    old_count = len(events)
    event = list(filter(lambda x: x.event_entry.event_type in SUPPORTED_EVENT_TYPES, events))
    new_count = len(event)
    logger.info(f'Filtered out {old_count - new_count} events (Reason: unsupported event type)')

    not_found_in_project_id_to_root = set()

    for event in event:
        if event.event_entry.parent_project_id not in project_id_to_root:
            not_found_in_project_id_to_root.add(event.event_entry.parent_project_id)
            continue
        mapping_data['root_project_id'].append(project_id_to_root[event.event_entry.parent_project_id].id)
        mapping_data['root_project_name'].append(
            project_id_to_root[event.event_entry.parent_project_id].project_entry.name)
        mapping_data['id'].append(event.id)
        mapping_data['title'].append(event.name)
        mapping_data['date'].append(event.date)
        mapping_data['type'].append(event.event_type)
        mapping_data['parent_project_id'].append(event.event_entry.parent_project_id)
        mapping_data['parent_project_name'].append(project_id_to_name.get(event.event_entry.parent_project_id, ''))
        mapping_data['parent_item_id'].append(event.event_entry.parent_item_id)

    logger.info(f'Processed {len(mapping_data["id"])} events')

    if len(not_found_in_project_id_to_root) > 0:
        logger.warning(f'Not found {len(not_found_in_project_id_to_root)} projects in project_id_to_root.')

    return DataFrame(mapping_data)
