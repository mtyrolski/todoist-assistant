# Windows uninstall behavior and remove-data option

## Implementation approach

- Default uninstall removes binaries and shortcuts only; ProgramData is preserved.
- A public MSI property `REMOVE_APPDATA` (default 0) controls optional data removal.
- The Burn bundle passes `REMOVE_APPDATA` into the MSI when set on the `TodometrySetup.exe` command line.
- MSI sets an internal `APPDATAREMOVE` property only when `REMOVE_APPDATA=1` on uninstall.
- `util:RemoveFolderEx` deletes the ProgramData root only when `APPDATAREMOVE` is set.
- A WiX Util `CloseApplication` action stops `todometry.exe` before uninstall/upgrade.

## Verification steps

1) Default uninstall preserves ProgramData
   - Install via `TodometrySetup.exe` and run the app to create `C:\ProgramData\Todometry`.
   - Uninstall via Apps & Features (or `TodometrySetup.exe /uninstall`).
   - Confirm `C:\ProgramData\Todometry` still exists and files remain.

2) Explicit remove-data uninstall
   - Run `TodometrySetup.exe /uninstall REMOVE_APPDATA=1 /quiet /norestart`.
   - Confirm `C:\ProgramData\Todometry` is removed.

3) Background process termination
   - Start `todometry.exe` (API/dashboard running).
   - Uninstall via Apps & Features.
   - Confirm the process is closed before file removal (no file-in-use errors).

4) Upgrade path safety
   - Install version N, then run `TodometrySetup.exe` for version N+1.
   - Confirm upgrade completes and ProgramData is preserved.
