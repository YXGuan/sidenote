# Set up sidenote

This is the first-run guide for people and local coding agents. Commands start
at the repository root. The macOS route includes a persistent local service.
The backend/build can also run on Unix-like systems using a foreground service;
native Windows setup is not validated.

## Clone, then ask your agent

```sh
git clone https://github.com/YXGuan/sidenote.git
cd sidenote
```

Open that directory in Claude Code or a ChatGPT/Codex agent with local filesystem
and terminal access. Paste this instruction:

```text
Set up sidenote in this checkout. Read AGENTS.md and docs/SETUP.md first,
then execute the setup and verification. Inspect the machine and existing vault;
ask for my Hypothesis username only if it is not configured. Install missing
prerequisites using the appropriate trusted package manager where authorized.
Run ./setup --check, then ./setup --user MY_USERNAME --install-service on macOS
(omit --install-service elsewhere). Replace MY_USERNAME with my actual username.
Reuse existing data and pairing; keep analysis local. Do not enable Codex,
import private annotations, or install daily jobs unless I request them.
Have me enter credentials directly in a hidden terminal
prompt if needed. Verify the built extension, local NLP, vault and bridge. Finish
browser installation and pairing where your tools allow, otherwise give me the
exact remaining steps. Do not call setup complete until those steps are verified.
```

An agent needs access to the cloned files and a terminal; a pasted prompt alone
does not give it access to your machine. The setup command below is also usable
directly without an agent.

## Prerequisites

Run the read-only check:

```sh
./setup --check
```

| Requirement | Why |
| --- | --- |
| Python 3.10+ with pip | Backend and local NLP; tested here with Python 3.14 |
| Node.js 22+ | Upstream client/extension builds; tested here with Node 22 |
| Git, Make, rsync | Pinned upstream clones and original extension Makefile |
| Chrome or a compatible Chromium browser | Load the unpacked extension |
| Internet during initial setup | PyPI packages, upstream Git clones, Yarn dependencies |
| Hypothesis username | Initializes your account scope; never use an example account |

Install missing tools before continuing. On macOS, the Command Line Tools supply
Git/Make; use your normal Python/Node installation or trusted package manager for
the required versions. macOS's bundled Python can be too old. If multiple Python
versions exist, invoke the chosen interpreter explicitly, e.g. `python3.14 setup`.
No global Yarn installation is required: pinned Yarn releases come with the
upstream repositories. The setup command installs Python packages under
`research-partner/.local-tools/python/`, leaving global Python packages alone.

## Run setup

Replace `YOUR_USERNAME` with your Hypothesis username, without `acct:` or a domain:

```sh
./setup --user YOUR_USERNAME --install-service
```

The command validates prerequisites and account ownership before changes,
installs the pinned local NLP packages if needed, initializes/reuses the vault,
reconstructs and builds the pinned Hypothesis sources, and installs/updates a
per-user macOS LaunchAgent. It listens only on `127.0.0.1:8765`, starts at login,
and does not require sudo. It does not change system DNS.

Rerunning setup preserves existing notes and credentials. For an initialized
vault, `--user` may be omitted. A different user is rejected; choose a separate
`--vault /absolute/path` instead. Only one bridge can occupy port 8765 at a time.
An unrelated listener is not stopped automatically. On a source update, read
the [development guide](DEVELOPMENT.md) before rebuilding modified nested clones.

For a foreground backend or another Unix-like OS:

```sh
./setup --user YOUR_USERNAME
# In a separate terminal, keep this process running:
./research-partner/notes serve
```

For a custom vault, use `./research-partner/notes --vault /absolute/path COMMAND`
for **every** subsequent command. The setup output prints the matching serve
command. Its service/schedule labels are derived from that vault's path.

## Connect Chrome

1. Open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**,
   and select the absolute `hypothesis/browser-extension/build/` directory.
2. Confirm the entry is **sidenote**, ID
   `lebpfahhlannplfhlllolppkmcapecge`. Keep the official extension installed if you
   use it; they have different IDs. Use one extension per article/tab at a time.
3. Open sidenote's **Extension options → Local research**. In your own
   terminal, run `./research-partner/notes pair` and save the printed local key
   in that form. It is a credential: do not paste it into a chat or commit it.
   Skip this step if the same browser profile is already paired.
4. Choose **Open local library** in the extension options, or open:

   ```text
   chrome-extension://lebpfahhlannplfhlllolppkmcapecge/client/notebook.html?local-library=1
   ```

The new library may be empty. Compact is the only layout. The library, dashboard
and collection tabs all share filters.
Choose Light, Dark, or System in **Settings → Appearance**; the header also has
a quick color-mode toggle. Dark mode follows the Console design.
See [the feature guide](../hypothesis/DASHBOARD.md).

After **every rebuild**, click **Reload** for sidenote in
`chrome://extensions`, then refresh the library and source tabs. This refreshes
the worker and client together. Existing pairing is retained.

## Optional account and data setup

Baseline local setup does not require any API keys or LLM account.

### Import public annotations

```sh
./research-partner/notes sync --public-only
```

This reads your configured user's public annotations into the local vault. It
does not publish anything. Refresh the library when it finishes.

### Connect your Hypothesis account and private annotations

Create/copy your developer token from your Hypothesis account settings. Run:

```sh
./research-partner/notes configure
```

Enter the token **directly into the hidden terminal prompt**. It is verified
against the configured username and saved in an ignored, mode-600 `.env` file;
never put a literal token in a shell command, chat, screenshot, or tracked file.
The default vault uses `research-partner/.env`; custom vaults use `.local/.env`.
Do not copy placeholder values from `.env.example` over existing credentials.

Then import the annotations accessible to that account:

```sh
./research-partner/notes sync
```

The local sidebar's **Log in** uses this paired backend account. Clicking the
original **Post to…** control publishes to Hypothesis with the selected sharing
setting. Local page metadata, reactions and collections remain in your vault.

### Automatic daily backup

Open the library's **Settings** tab, enable **Back up automatically every day**,
choose a local time and import scope, then **Save settings**. Public-only imports
need no token; authenticated imports use the verified account configured above.
Automatic backup is off until enabled. **Back up now** also lives in Settings.

The existing local bridge runs the daily job, including with Chrome closed. It
catches up when the computer wakes or the bridge restarts, retries failed imports
after an hour, and saves a local snapshot even if annotation import fails. Keep
the bridge running (the installed macOS service already does this). On other
Unix systems, keep the foreground `notes serve` process running.

For a separate macOS daily sync job, the CLI option remains available:

After configuring a verified token, optionally install the daily sync job:

```sh
./research-partner/notes schedule --install
```

Alternatively, `schedule --public-only --install` needs no account token. The job
runs at 03:00 local time and on load, separately from the bridge; sleep/offline
time may delay runs. Remove only that job with `schedule --uninstall`.

### Optional scholarly keys and Codex

OpenAlex/Semantic Scholar keys improve research enrichment; they are not needed
to build, open the library, or run local NLP collections. Enter them directly in
**Settings → API keys**, then **Save settings**. Existing key values are never
displayed. Blank fields retain them; **Remove key** removes a saved key when the
form is saved. The bridge preserves other credentials in the existing ignored,
owner-only `.env` file. Environment-managed keys must be changed in the service
environment instead. Do not paste keys into chat.

**Settings → Research enrichment** controls automatic incremental enrichment.
With an API key configured, new/changed/expired sources are processed after
changes and on a 15-minute check. Fresh cached records are skipped entirely.
**Enrich research** performs the same incremental pass manually.

Topic classification uses local taxonomy rules by default. NLTK and VADER power
automatic question/liked collections locally. Optional GPT-6 Luna analysis uses
the user's signed-in Codex CLI and transmits selected context only when enabled.
See [classification and model setup](../research-partner/docs/CLASSIFICATION.md).
Do not enable Codex or install its CLI merely to complete baseline setup.

The **Research** workspace adds local natural-language retrieval, wiki exports,
and graph browsing. Ask + web, related-term expansion, and topic synthesis are
explicit model actions using that same signed-in CLI. See the [Research guide](../research-partner/docs/RESEARCH-WORKSPACE.md).

### Optional Zotero connection

Open **Settings → Zotero** to connect your personal/group online library using a
dedicated Zotero API key, or read the desktop library on the same computer through
its local API. Enter keys directly in Settings or the CLI's hidden prompt. RIS/CSL
JSON file exchange is also available. See the [Zotero guide](ZOTERO.md).

## Verify the installation

| Check | Command or observation | Expected result |
| --- | --- | --- |
| Tools | `./setup --check` | `ready: true` |
| Built extension | `python3 -c 'import json; print(json.load(open("hypothesis/browser-extension/build/manifest.json"))["name"])'` | `sidenote` |
| Local NLP | `python3 -c 'import sys; sys.path.insert(0,"research-partner"); from research_notes.collections import tools; tools(); print("Local NLP ready")'` | No download, then `Local NLP ready` |
| Account/vault | `./research-partner/notes doctor --json` | Correct username/vault; a fresh document count may be zero |
| Bridge | `curl --fail http://127.0.0.1:8765/health` | `ok: true`, service `research-notes` |
| macOS service | `./research-partner/notes service --status` | Installed, loaded, running are true |
| Browser | Extension options → Open local library | Library loads without pairing/offline errors |
| Persistence | Reload extension, refresh library | Saved pairing/data remain; no duplicate extension required |

Do not infer successful browser installation from a successful build or health
check. If the agent cannot access an extension page, it should give the user the
remaining Chrome steps and ask for the observed result, without bypassing access
restrictions or claiming to have verified them.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Missing Python/Node/Make/rsync | Read `./setup --check`; fix the missing tool/version, then rerun |
| pip is missing | Use a Python distribution with pip; do not install into system Python with sudo |
| Clone/package download fails | Check network/proxy/CA configuration; retry without disabling TLS verification |
| Upstream patch does not apply | Read nested `git status` and pinned commits; preserve edits; see [development](DEVELOPMENT.md#native-patches) |
| Port 8765 is occupied | Identify its owner. Reuse the correct bridge or stop your own foreground process; don't kill an unrelated listener |
| Bridge is offline | Start `notes serve` or check `service --status`; inspect protected `.local/bridge-error.log` locally |
| Pairing error after a rebuild | Reload sidenote in `chrome://extensions` and refresh its tabs before re-pairing |
| Log in fails | Run `notes configure` for the vault's username; verify the bridge is running |
| Library is empty | Fresh installs contain no data; save a page or run your chosen sync command |
| Automatic collections unavailable | Verify local NLP with the command above; rerun setup to install missing dependencies |
| Visit Often is empty | It needs 3 visits in 30 days; old browser history is not imported; visits within 5 minutes count once |

The bridge and vault stay on disk after closing the browser. `notes service
--uninstall` removes the macOS bridge job without deleting notes. Moving the
checkout requires reinstalling its service/job at the new path and loading the
new extension build directory; retain the existing vault and credentials.
