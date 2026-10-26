# Connect Zotero to sidenote

Open sidenote's **Settings → Zotero**. You can read the desktop library directly,
or connect your synced personal/group library through Zotero's online API.
Both save references and notes to your local vault. Imports do not modify Zotero.

## Connect the online library

1. Open [Zotero API key settings](https://www.zotero.org/settings/keys). Create a
   dedicated key with read access to your library and notes; write access is not
   needed. Note the numeric user ID shown there. For a group library, use its
   numeric group ID and grant the key access to that group.
2. Under **Settings → Zotero → Connect your online library**, choose Personal or
   Group, enter that ID and API key, then **Save Zotero connection**. Enter the key
   directly in the local form or hidden CLI prompt; do not put it in chat.
3. Choose **Import from Zotero online**. Repeat to refresh from your synced library.
   Zotero desktop can be closed. Unsynced desktop edits are available only through
   the desktop connection until Zotero syncs them.

Large direct imports run in the backend while the extension polls for completion.
Keep the backend running; closing the Settings tab does not cancel an import.

Keys are stored in the existing ignored, owner-only `.env` credential file and
sent only to `https://api.zotero.org` in an authentication header. Saved key values
are never returned to the UI, included in backups, or passed to model subprocesses.
Blank key fields keep the saved key; **Remove Zotero key** plus **Save Zotero
connection** removes it locally. Environment-managed keys must be changed in the
service environment. This integration issues only read requests to Zotero.
See [Zotero's API documentation](https://www.zotero.org/support/dev/web_api/v3/basics).

## Connect the desktop library

The desktop connection needs no API key and keeps all communication on this computer.

1. Open Zotero on the same computer as the sidenote backend.
2. In Zotero, enable **Settings → Advanced → Allow other applications on this
   computer to communicate with Zotero**.
3. In sidenote, choose **Import from Zotero desktop**.
4. Repeat that action to refresh references and notes after editing them in Zotero.

This uses Zotero's documented [local API](https://www.zotero.org/support/dev/web_api/v3/local_api)
on `127.0.0.1:23119`. If your Zotero version does not offer this setting, update
Zotero or use file exchange below. The backend must run on the same computer;
opening Zotero only on another device will not connect it.

Both connections import titles, authors, dates, DOI/URL, publication information,
abstracts, tags, child notes, and PDF annotation text/comments. Imported notes
appear in saved-page details and local search. They remain separate from your
Hypothesis annotations. Desktop reads the personal library; online can read a
personal or group library. Standalone
notes, attachment files, PDF positions/colors, collection folders, and ongoing
automatic or two-way synchronization are not included. Local edits in sidenote
are exported explicitly rather than written back through the desktop connection.

Repeated imports match Zotero item identities, DOI, and source URLs. They retain
manual titles, citation corrections (including intentionally cleared fields),
tags, reactions, personal Markdown notes, and removed items. Items deleted in
Zotero are retained in sidenote. Original import evidence is saved in `imports/`,
current reference data in `references/`; both are included in snapshots. Neither
directory contains connection credentials. Imported text is treated as data.

## Exchange files

To bring selected Zotero items into sidenote, select them in Zotero, choose
**Export Items**, select **RIS**, and enable **Export notes**. In sidenote, choose
that `.ris` file under **Settings → Zotero → Import reference file**. CSL JSON
exports (`.json`) are also supported for references only. Files must contain
UTF-8 text and be no larger than 10 MB.

To send your sidenote library to Zotero, choose **Export library for Zotero**,
then in Zotero choose **File → Import → A file** and select the downloaded file.
RIS includes references and tags; check **Include highlights, comments and
personal notes** to add those as Zotero notes. CSL JSON contains citation metadata
only. Export includes the entire visible library, including sources outside the
current filters, and excludes items you removed. Empty libraries export zero
references.

Zotero [supports these interchange formats](https://www.zotero.org/support/kb/importing_standardized_formats).
Its [field mapping guide](https://www.zotero.org/support/kb/field_mappings) explains
format limitations: file exchange does not preserve a complete Zotero library or
existing word processor citation links. Repeated imports into Zotero can create
duplicates; use Zotero's duplicate detection when appropriate.

## Command line

Run from the repository root. For a custom vault, place `--vault /absolute/path`
before `zotero`, as with other commands.

```sh
# Read the running local Zotero desktop library.
./research-partner/notes zotero desktop

# Configure online access; the key is entered through a hidden prompt.
# Replace YOUR_NUMERIC_ID with your numeric Zotero user/group ID.
./research-partner/notes zotero configure --library-type users --library-id YOUR_NUMERIC_ID
./research-partner/notes zotero online

# Import a Zotero export without opening Zotero.
./research-partner/notes zotero import /path/to/references.ris
./research-partner/notes zotero import /path/to/references.json --format csl-json

# Export to a new file. Existing files are never overwritten.
./research-partner/notes zotero export /path/to/sidenote.ris --include-notes
./research-partner/notes zotero export /path/to/sidenote.json --format csl-json

# Use --document DOCUMENT_ID repeatedly to export a selection.
```

For development builds, follow [the development guide](DEVELOPMENT.md). Restart
the local backend and reload sidenote in Chrome after updating the built extension;
then refresh the library tab. Building the extension does not reload Chrome's copy.
