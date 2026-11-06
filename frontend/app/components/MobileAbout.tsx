"use client";

import { useState } from "react";

export function MobileAbout({ version, preview }: { version?: string; preview?: boolean }) {
  const [licenses, setLicenses] = useState("");
  return (
    <details className="card">
      <summary>Privacy &amp; app info</summary>
      {version && (
        <p className="muted tiny">
          Version {version}
          {preview ? " · Preview" : ""}
        </p>
      )}
      <p>This app reads your Todoist projects, tasks and activity. It does not edit your Todoist account.</p>
      <p>
        Your API token is sent only to Todoist over HTTPS. It is stored on this device using Android Keystore
        encryption. Task history and preferences are stored in this app’s private files.
      </p>
      <p>
        There are no ads, analytics SDKs or developer servers receiving your task history. The demo uses
        sample data and does not need a token.
      </p>
      <p>
        Disconnect removes saved history, the token and local settings. This does not delete your Todoist
        account or change its tasks. You can also remove all local data in Android’s app settings.
      </p>
      <p className="muted tiny">An independent third-party integration. Not affiliated with or endorsed by Doist. Todoist and Doist are trademarks of their owners.</p>
      <button
        className="button buttonSmall buttonGhost"
        onClick={async () => {
          if (licenses) {
            setLicenses("");
            return;
          }
          try {
            const response = await fetch("/third-party-notices.txt");
            if (!response.ok) throw new Error();
            setLicenses(await response.text());
          } catch {
            setLicenses("Could not open licenses. Reopen the app and try again.");
          }
        }}
      >
        Open-source licenses
      </button>
      {licenses && (
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12 }}>{licenses}</pre>
      )}
    </details>
  );
}
