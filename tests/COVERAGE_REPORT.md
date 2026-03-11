V# Pytest Coverage Report

Coverage snapshot generated on 2026-03-11 from the full `tests/` pytest suite against the `todoist` package.

## Summary

- Overall line coverage: `51.06%`
- Covered lines: `3516 / 6886`
- Missing lines: `3370`
- Excluded lines: `157`
- Pytest result: `293 passed`, `2 failed`, `3 skipped`, `1 warning`

## Commands used

```powershell
$env:UV_PROJECT_ENVIRONMENT='C:\Users\micha\AppData\Local\Temp\todoist-assistant-coverage-env'
$env:COVERAGE_FILE='C:\Users\micha\AppData\Local\Temp\todoist-assistant.coverage'
uv run --with coverage python -m coverage run --source=todoist -m pytest tests
uv run --with coverage python -m coverage json -o coverage.json
uv run --with coverage python -m coverage report
```

## Failing tests

1. `tests/test_utils.py::test_load_config_with_absolute_path`
   Current behavior on this environment calls `initialize(config_path='/tmp/todoist-config')` instead of `initialize_config_dir(...)`.
2. `tests/windows/test_windows_installer.py::test_windows_msi_contents`
   No built MSI was present under `dist/windows`, so the packaging smoke test fails until an installer is built.

## Lowest-covered modules

| Module | Coverage | Statements | Missing |
| --- | ---: | ---: | ---: |
| `todoist\automations\init_env\__init__.py` | 0.0% | 4 | 4 |
| `todoist\automations\run\__init__.py` | 0.0% | 4 | 4 |
| `todoist\automations\update_env\__init__.py` | 0.0% | 4 | 4 |
| `todoist\run_observer.py` | 0.0% | 18 | 18 |
| `todoist\automations\run\automation.py` | 0.0% | 24 | 24 |
| `todoist\agent\context.py` | 0.0% | 30 | 30 |
| `todoist\automations\init_env\automation.py` | 0.0% | 32 | 32 |
| `todoist\automations\update_env\automation.py` | 0.0% | 33 | 33 |
| `todoist\agent\chat.py` | 0.0% | 62 | 62 |
| `todoist\telemetry.py` | 0.0% | 103 | 103 |
| `todoist\cli.py` | 0.0% | 152 | 152 |
| `todoist\automations\llm_breakdown\automation.py` | 0.0% | 191 | 191 |
| `todoist\automations\llm_breakdown\runner.py` | 0.0% | 227 | 227 |
| `todoist\launcher.py` | 0.0% | 259 | 259 |
| `todoist\database\dataframe.py` | 16.0% | 94 | 79 |

## Highest-covered modules

| Module | Coverage | Statements | Missing |
| --- | ---: | ---: | ---: |
| `todoist\dashboard\utils.py` | 100.0% | 42 | 0 |
| `todoist\env.py` | 100.0% | 36 | 0 |
| `todoist\constants.py` | 100.0% | 32 | 0 |
| `todoist\stats.py` | 100.0% | 28 | 0 |
| `todoist\agent\graph.py` | 100.0% | 25 | 0 |
| `todoist\automations\gmail_tasks\contracts.py` | 100.0% | 25 | 0 |
| `todoist\automations\activity\automation.py` | 100.0% | 23 | 0 |
| `todoist\automations\gmail_tasks\constants.py` | 100.0% | 22 | 0 |
| `todoist\api\endpoints.py` | 100.0% | 18 | 0 |
| `todoist\agent\constants.py` | 100.0% | 14 | 0 |
| `todoist\dashboard\tasks.py` | 100.0% | 13 | 0 |
| `todoist\llm\types.py` | 100.0% | 10 | 0 |
| `todoist\api\__init__.py` | 100.0% | 3 | 0 |
| `todoist\llm\__init__.py` | 100.0% | 3 | 0 |
| `todoist\agent\__init__.py` | 100.0% | 2 | 0 |

## Full module table

```text
Name                                              Stmts   Miss  Cover
---------------------------------------------------------------------
todoist\__init__.py                                   0      0   100%
todoist\activity.py                                  53     40    25%
todoist\agent\__init__.py                             2      0   100%
todoist\agent\chat.py                                62     62     0%
todoist\agent\constants.py                           14      0   100%
todoist\agent\context.py                             30     30     0%
todoist\agent\graph.py                               25      0   100%
todoist\agent\nodes.py                              189     51    73%
todoist\agent\prefabs.py                             23      5    78%
todoist\agent\repl_tool.py                          119     21    82%
todoist\agent\utils.py                               17      1    94%
todoist\api\__init__.py                               3      0   100%
todoist\api\client.py                               150     33    78%
todoist\api\endpoints.py                             18      0   100%
todoist\automations\__init__.py                       0      0   100%
todoist\automations\activity\__init__.py              9      1    89%
todoist\automations\activity\automation.py           23      0   100%
todoist\automations\base.py                          33      7    79%
todoist\automations\gmail_tasks\__init__.py           9      1    89%
todoist\automations\gmail_tasks\automation.py       211     35    83%
todoist\automations\gmail_tasks\constants.py         22      0   100%
todoist\automations\gmail_tasks\contracts.py         25      0   100%
todoist\automations\gmail_tasks\helpers.py           57      4    93%
todoist\automations\init_env\__init__.py              4      4     0%
todoist\automations\init_env\automation.py           32     32     0%
todoist\automations\llm_breakdown\__init__.py         9      5    44%
todoist\automations\llm_breakdown\automation.py     191    191     0%
todoist\automations\llm_breakdown\config.py          37     27    27%
todoist\automations\llm_breakdown\models.py          96     36    62%
todoist\automations\llm_breakdown\runner.py         227    227     0%
todoist\automations\multiplicate\__init__.py          9      1    89%
todoist\automations\multiplicate\automation.py      265     30    89%
todoist\automations\observer\__init__.py              9      1    89%
todoist\automations\observer\automation.py           64     19    70%
todoist\automations\run\__init__.py                   4      4     0%
todoist\automations\run\automation.py                24     24     0%
todoist\automations\template\__init__.py              9      1    89%
todoist\automations\template\automation.py          106     67    37%
todoist\automations\update_env\__init__.py            4      4     0%
todoist\automations\update_env\automation.py         33     33     0%
todoist\cli.py                                      152    152     0%
todoist\constants.py                                 32      0   100%
todoist\dashboard\__init__.py                         0      0   100%
todoist\dashboard\plots.py                          570    144    75%
todoist\dashboard\tasks.py                           13      0   100%
todoist\dashboard\utils.py                           42      0   100%
todoist\database\base.py                             28     15    46%
todoist\database\dataframe.py                        94     79    16%
todoist\database\db_activity.py                     138     55    60%
todoist\database\db_labels.py                        69     53    23%
todoist\database\db_projects.py                     254    117    54%
todoist\database\db_tasks.py                        102     15    85%
todoist\database\demo.py                             81     27    67%
todoist\env.py                                       36      0   100%
todoist\launcher.py                                 259    259     0%
todoist\llm\__init__.py                               3      0   100%
todoist\llm\llm_utils.py                             79     58    27%
todoist\llm\local_llm.py                            395    189    52%
todoist\llm\types.py                                 10      0   100%
todoist\run_observer.py                              18     18     0%
todoist\stats.py                                     28      0   100%
todoist\telemetry.py                                103    103     0%
todoist\types.py                                    185     21    89%
todoist\utils.py                                    317     22    93%
todoist\version.py                                   16     10    38%
todoist\web\__init__.py                               0      0   100%
todoist\web\api.py                                 1645   1036    37%
---------------------------------------------------------------------
TOTAL                                              6886   3370    51%
```
