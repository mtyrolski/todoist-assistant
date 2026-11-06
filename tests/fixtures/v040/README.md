Synthetic v0.4.0 compatibility fixture
======================================

These files contain no user data. The joblib files were generated with
`LocalStorage`, `Event`, `EventEntry`, `Project` and `ProjectEntry` from git tag
`todois-assistant-v0.4.0` (commit `9d26315ca2c79bdaf70b472ea785a8c663144d76`)
using the current test environment's joblib and pandas versions. The dashboard
snapshot uses the version 3 schema and contains a representative archived
project and activity frame. `dashboard.yaml` comes directly from that tag;
project mappings and the observer and removed-feature cache are synthetic.

The fixture exercises legacy serialized class names through the small
`todoist.core.types` compatibility shim, including a copy to the new default
state location. Native installer upgrades still require platform validation.
