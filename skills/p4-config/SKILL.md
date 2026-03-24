---
name: p4-config
description: Switch between Perforce (P4) servers and download files from P4 depots. Use this skill whenever the user wants to switch P4 servers, change Perforce connection, or mentions "p4 switch", "p4 server", "switch perforce", "change p4 port". Also trigger when the user asks "which P4 server am I on" or wants to check/view current P4 settings. ALSO trigger when the user provides a Perforce depot path (starting with "//") and wants to download, sync, print, or view a file from P4 — e.g., "download //depot/project/doc/file.pdf" or "get //depot/path/to/file".
compatibility:
  tools: [Bash, Glob, Read, AskUserQuestion]
---

# P4

Manages Perforce server configurations and depot operations — switch servers, download files, and more.

## Config file convention

Config files use the naming pattern `.p4config.<CONFIG_NAME>`, where the extension after `.p4config.` is a human-friendly config name chosen by the user (e.g., `.p4config.austin`, `.p4config.atlanta`).

Each config file contains one `KEY=VALUE` per line. Supported keys: `P4PORT`, `P4USER`, `P4CLIENT`, and any other `P4*` environment variable. Blank lines and lines starting with `#` are ignored.

See `assets/.p4config.example` for a template.

## How settings are applied

Use `p4 set KEY=VALUE` to apply each setting. On Windows this writes to the registry; on macOS/Linux it writes to `~/.p4enviro`. Either way, settings persist across all shells without needing to source or export anything — which is important because shell env vars don't survive between Bash calls in Claude Code.

## Workflow

### 1. Discover available configs

Search for `.p4config.*` files. Check these locations in order, using the first one that has matches:

1. The current working directory
2. The user's home directory (`$HOME` or `$USERPROFILE`)

Use Glob with pattern `.p4config.*` in each location.

Extract the config name from each filename — the part after `.p4config.` is the config name.

Parse each file to extract all `KEY=VALUE` pairs (skip blank lines and lines starting with `#`).

If no config files are found, tell the user and explain how to create one (point them to `assets/.p4config.example` in this skill's directory for a template).

### 2. Show current settings

Run `p4 set` to display what the user currently has active, so they can see what will change.

### 3. Prompt the user

Use AskUserQuestion to present the available configs:

- **Label**: the config name from the filename (e.g., `austin`)
- **Description**: the `P4PORT` and `P4USER` from that config file

### 4. Apply the selected config

For each `KEY=VALUE` pair in the chosen config file, run `p4 set KEY=VALUE`. Chain all of them with `&&` in a single Bash call. Only set keys that have non-empty values.

### 5. Verify

Run `p4 set` to confirm the new settings, and show the result to the user.

## Downloading files from a depot path

When the user provides a Perforce depot path (anything starting with `//`), download the file using the currently active P4 server. Follow this logic:

### 1. Check if a P4 server is already configured

Run `p4 set` and look for `P4PORT`. If `P4PORT` is set, skip to step 3.

### 2. No server configured — help the user pick one

Search for `.p4config.*` files (same discovery logic as the switch workflow above).

- **Configs found**: Use AskUserQuestion to prompt the user to choose a config, then apply it with `p4 set`.
- **No configs found**: Ask the user if they want to create a config file. Point them to `assets/.p4config.example` in this skill's directory as a template. Do not proceed until a server is configured.

### 3. Download the file

Use `p4 print -o <output_path> <depot_path>` to download.

- Save to the `download/` subdirectory under the current working directory. Create the directory if it doesn't exist.
- Preserve the original filename from the depot path.
- If the download fails with a connection error, inform the user and suggest switching servers or checking network/VPN.

### 4. Confirm

Tell the user the local path where the file was saved.

## Adding new configs

If the user wants to add a new config:

1. Ask for the server connection details in a **single prompt** using AskUserQuestion with three questions at once:
   - **Protocol**: `tcp` (Recommended) or `ssl`
   - **Server hostname**: the server address (e.g., `myserver.example.com`)
   - **Port**: the port number (e.g., `1666`)
   Then combine them into `P4PORT=<protocol>:<hostname>:<port>`.
   Also ask for `P4USER` in the same prompt. Optionally ask for `P4CLIENT` (not required — many operations like `p4 print` work without it).
2. Ask for a short config name to use in the filename (e.g., `austin`).
3. Ask where to store the config file using AskUserQuestion:
   - **Current working directory (Recommended)** — the default, keeps configs alongside the project
   - **Home directory** — `$HOME` or `$USERPROFILE`, useful if the config should be available from anywhere
4. Read `assets/.p4config.example` from this skill's directory. Use it as the base template — keep the comment block structure, replace the placeholder values (`your-server-host`, `your-username`, `your-client-name`) with the user's actual values, and update the `CONFIG_NAME` in the comments. If the user chose to skip `P4CLIENT`, omit that line entirely. Write the result as `.p4config.<CONFIG_NAME>` in the chosen location.
