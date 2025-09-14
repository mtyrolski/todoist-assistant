# Hydra Configuration Structure

This directory contains the refactored Hydra configuration for the todoist-assistant automations. The configuration has been restructured to be more maintainable and organized.

## Structure

```
configs/
├── automations.yaml              # Main configuration file (clean and simple)
├── automations_original_backup.yaml  # Backup of original monolithic config
├── templates.yaml                # Template definitions organized by category
├── automations/                  # Individual automation configurations
│   ├── activity.yaml            # Activity automation settings
│   ├── multiply.yaml            # Multiply automation settings  
│   └── template.yaml            # Template automation configuration
└── templates/                   # Individual template files (organized by category)
    ├── development/             # Development-related templates
    │   ├── pr.yaml             # Pull request review template
    │   └── feature.yaml        # Feature development template
    ├── academic/               # Academic/research templates
    │   ├── conference_people_scan.yaml
    │   ├── networking_reachout.yaml
    │   ├── networking_followup.yaml
    │   ├── talk_attendance.yaml
    │   ├── conference_paper_scan.yaml
    │   ├── summer_school_project_team.yaml
    │   ├── conference_postmortem.yaml
    │   ├── poster_creation.yaml
    │   └── read_paper.yaml
    └── communication/          # Communication templates
        ├── msg.yaml           # Message template
        └── call.yaml          # Call/meeting template
```

## Benefits of the New Structure

1. **Modularity**: Each template is in its own file and can be modified independently
2. **Organization**: Templates are grouped by category (development, academic, communication)
3. **Maintainability**: The main config file is much smaller and easier to read
4. **Composition**: Uses Hydra's composition features for clean config assembly
5. **Extensibility**: Easy to add new templates or categories

## Usage

The configuration works exactly the same as before. Use:

```bash
# For environment initialization
make init_local_env

# For environment updates  
make update_env

# For running automations
python3 -m todoist.automations.run --config-dir configs --config-name automations
```

## Adding New Templates

1. Create a new template file in the appropriate category directory under `templates/`
2. Add the template reference to `templates.yaml`
3. Add the template reference to `automations/template.yaml`

The hierarchical structure makes it easy to understand and maintain the various automation templates.