# Windows prerequisite detection test matrix

## Visual C++ 2015-2022 Redistributable (x64)

| Scenario | Precondition | Expected result | Verification steps |
| --- | --- | --- | --- |
| Fresh machine (no VC++ x64) | Registry key missing: `HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64` | Bundle installs `vc_redist.x64.exe` before MSI; `setup.exe` completes | 1) Remove the key or uninstall VC++ x64. 2) Run `setup.exe` UI install. 3) Confirm `vc_redist.log` shows install. 4) Confirm registry `Installed=1` afterward. |
| VC++ already installed | Registry key exists with `Installed=1` | Bundle skips `vc_redist.x64.exe` and proceeds to MSI | 1) Ensure VC++ x64 is installed. 2) Run `setup.exe`. 3) Confirm `vc_redist.log` shows no install action. |
| Silent install | Same as above | `vc_redist` runs only when missing, always `/quiet /norestart` | 1) Run `setup.exe /quiet /norestart /log <path>`. 2) Check logs under `C:\ProgramData\TodoistAssistant\logs\installer`. |
| Reboot requested by redist | Force a redist return of 3010/1641 (or simulate via test VM snapshot) | Bundle surfaces restart required message; no automatic reboot | 1) Install on VM where VC++ triggers restart. 2) Confirm UI shows restart required. 3) Validate no automatic reboot was forced. |

## Repair behavior

| Scenario | Precondition | Expected result | Verification steps |
| --- | --- | --- | --- |
| Re-run setup.exe with product installed | Bundle registered in Apps & Features | Bootstrapper shows Repair/Uninstall | 1) Install via `setup.exe`. 2) Re-run `setup.exe`. 3) Verify Repair option is offered. |
| Repair executes MSI | App files modified/removed | MSI repair runs and restores files | 1) Delete an installed file under `C:\Program Files\TodoistAssistant`. 2) Run Repair. 3) Confirm file restored and MSI log indicates repair. |
