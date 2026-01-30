# Windows uninstall behavior and remove-data option

## Implementation approach

- Default uninstall removes binaries and shortcuts only; ProgramData is preserved.
- A public MSI property `REMOVE_APPDATA` (default 0) controls optional data removal.
- The Burn bundle passes `REMOVE_APPDATA` into the MSI when set on the setup.exe command line.
- MSI sets an internal `APPDATAREMOVE` property only when `REMOVE_APPDATA=1` on uninstall.
- `util:RemoveFolderEx` deletes the ProgramData root only when `APPDATAREMOVE` is set.
- A WiX Util `CloseApplication` action stops `todoist-assistant.exe` before uninstall/upgrade.

## Verification steps

1) Default uninstall preserves ProgramData
   - Install via `setup.exe` and run the app to create `C:\ProgramData\TodoistAssistant`.
   - Uninstall via Apps & Features (or `setup.exe /uninstall`).
   - Confirm `C:\ProgramData\TodoistAssistant` still exists and files remain.

2) Explicit remove-data uninstall
   - Run `setup.exe /uninstall REMOVE_APPDATA=1 /quiet /norestart`.
   - Confirm `C:\ProgramData\TodoistAssistant` is removed.

3) Background process termination
   - Start `todoist-assistant.exe` (API/dashboard running).
   - Uninstall via Apps & Features.
   - Confirm the process is closed before file removal (no file-in-use errors).

4) Upgrade path safety
   - Install version N, then run setup.exe for version N+1.
   - Confirm upgrade completes and ProgramData is preserved.
