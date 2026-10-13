# Dunkin store price comparison

## Free local AI: Ollama

The app now supports **Free local (Ollama)** in AI settings. Install the free
Ollama app, open it, and run **Prepare Free AI Mac.command** once to download
`gemma3:4b`, an image-capable local model. Then enable AI discovery with the local
provider and click Run now. No API key or per-run AI fee is required. A several-GB
model download and sufficient RAM are required; 16 GB+ is recommended, and Intel
or low-memory machines may be slow. The app includes no model weights in its ZIP.

The local planner uses Ollama's `/api/chat` with screenshots, structured page
evidence and JSON actions. Requests are fixed to `127.0.0.1:11434`, do not inherit
HTTP proxies, and refuse redirects. Cloud-model names and models with reported
remote backends are rejected; there is no paid-API fallback. Local readiness checks
query installed models and vision capability without generating tokens. Page
evidence is limited to on-screen/store-context elements to reduce local context
size. Price/store/channel validation is shared with the paid planner.

Local mode preserves the existing browser, Excel and scheduling workflows, but
smaller models may fail to navigate complex menus. It requires an initial run to
review results; full-menu coverage remains unverified. The local API contract and
readiness checks are mocked in tests, and the shared browser is exercised against
synthetic pages. **Actual Ollama inference has not been tested in this environment**;
official Ollama documentation requests were blocked by the cloud network policy.
Native Mac installation and live Dunkin still need validation on your Mac.

To update, disable any older schedule, extract the new ZIP to a new folder and
rerun Setup Mac.command. Install/open Ollama, prepare the model, then choose the
free provider explicitly. Existing paid-mode settings do not silently switch.

## Optional paid AI page discovery: no teaching required

The desktop app now has **AI settings**. With an OpenAI API key and separate API
billing, enable AI discovery and click **Run automatically now**. The planner
receives a screenshot and numbered DOM evidence each step, searches for the store,
chooses menu controls, opens categories/items/options, and collects observed prices.
It runs afresh on each job rather than relying on taught selectors. Existing guided
collection and taught layouts remain optional alternatives.

API keys are entered only in the local app and stored with the native Mac Keychain
or Windows Credential Manager. Linux can use `OPENAI_API_KEY`. No credentials are
saved in source, settings JSON, traces, logs, GitHub, or bundles. During AI runs,
ordering-page screenshots and extracted page text are sent to OpenAI's API. The
default planner is `gpt-4.1-mini` using the Chat Completions API. A ChatGPT subscription
does not include API usage. Daily AI scheduling requires an explicit confirmation.
The configurable 1–200 calls-per-store limit bounds calls, **not dollar spending**.

The model cannot supply free-form prices to the exporter: it must cite current
DOM elements for selected-store address, active channel, name, category, variant,
and an exact dollar price. Addresses accept standard street abbreviations while
requiring the numbered street, city, and state. Name and price must share a small
card/dialog; inactive variant/category controls, changed evidence, ranges, inferred
currencies, unobserved IDs, and conflicting prices are rejected. Only address-search
fields may be filled, only configured addresses may be entered, and unobserved select
options are rejected. Checkout, login and add-to-cart controls are blocked. API
credentials are never given to the planner. Page text is treated as untrusted data.

The renderer currently inspects DOM-backed controls in the main document; embedded
frames, canvas-only controls, unusual markup, and nonstandard selected-store/channel
labels may fail. For a provider that cannot be reached automatically, an optional
ordering URL can be entered in the store editor. This is a bounded AI navigation
loop, not guaranteed autonomous coverage of every site/menu. Completion is the AI's
assessment; **full-menu coverage is not independently verified**. Already validated
rows from a blocked/budget-limited run are retained with `partial` status. Three
consecutive validation errors stop that store; no price estimates are substituted.

Browser traversal and option extraction are tested in real Chromium with synthetic
pages and a scripted planner; provider payload/error handling is mocked. **No live
paid AI calls were made**, and live Dunkin behavior, Mac Keychain access, native
desktop UI and OS scheduling still require real-machine validation. Use the first
run to review Excel against the actual menu before relying on scheduled comparisons.

Download the updated package, extract to a new folder, and rerun setup to install
the new `keyring` dependency. If an older folder has a daily schedule, disable it
there first. Your existing address CSVs can be copied into the new folder's `data`
directory; keep session files and API keys local.

Download the [Mac agent ZIP](https://github.com/mhaque16/HelloWorld/raw/refs/heads/master/downloads/DunkinPriceAgent-Mac.zip).
If the direct download does not open, use its [GitHub file page](https://github.com/mhaque16/HelloWorld/blob/master/downloads/DunkinPriceAgent-Mac.zip)
and click **Download raw file**. Mac setup instructions are in `START_HERE_MAC.txt`.

## Mac desktop version

Download and extract `DunkinPriceAgent-Mac.zip` into a permanent folder inside your
home folder (Finder > Go > Home). Install Python 3.12+ with the python.org macOS
installer, double-click **Setup Mac.command** once, then **Open Agent Mac.command**.
The Mac version includes the same store editor, teaching workflow, Run now, and
Excel export. See `START_HERE_MAC.txt` for a simple walkthrough.

Daily autorun uses a per-user LaunchAgent in `~/Library/LaunchAgents`. Enable it
from the app after teaching and a successful automatic test. It uses your Mac's
local clock and runs in your own login session; the Mac must be awake and signed
in. Disable it before moving the folder. Newer macOS versions may require enabling
the background item in System Settings. Session files stay local and are excluded
from the ZIP. This is a Python application with executable `.command` launchers,
not a signed macOS `.app`. Native Mac launchers and launchd still need Mac testing.

Build the Mac bundle with `python scripts/build_mac_bundle.py`.

Python tool for collecting location-specific menu prices and exporting an Excel
comparison of parent and competitor stores. Both groups are Dunkin US locations.

**PC workflow:** a visible browser opens with a Menu Price Collector panel. Select
the store yourself, click displayed item names and prices, review the captured
rows, and export Excel. This assisted workflow needs no site-specific selectors
or menu URLs. Field picking, bulk preview, confirmation, navigation, and export
are tested with synthetic pages in actual Chromium. Dunkin's live ordering
interface and the Windows launchers have not been tested here.

A verified Dunkin-specific extraction profile is not implemented. AI mode attempts
generic store search from observed page controls, but still needs live validation.
The national menu is not a source of store-specific prices.

## Desktop agent: one-click and daily runs

After Windows setup, open **open_agent.bat**. The desktop app lets you edit both
store lists, teach menu pages, run now, open reports, and enable/disable daily
autorun. No CSV editing or terminal commands are needed after installation.

For the optional taught-layout mode, select each store and **Teach selected store**. On its actual ordering page,
confirm the selected store/channel and pick visible address, category, size,
item-name and price text. Preview and review all similar cards, then **Teach
autorun this page**. Repeat for every page you want covered. Finish teaching,
then **Run automatically now**. Daily scheduling is enabled only after a
successful automatic run for every configured store.

Each taught page has its own layout and locally saved browser session. Automatic
runs open fresh headless browser contexts, restore those sessions, and verify
the selected-store text and shared category/size text before reading prices.
If these checks fail, the store has no price rows and the failure is recorded.
Address/channel edits invalidate teaching. Conflicting prices are rejected.
Jobs use a process lock to prevent overlapping scheduled/manual runs.

Taught-layout autorun covers **only taught pages**, not the full menu by default. It does not
replay store-selection clicks, category tabs, or size-option dialogs. If those
selections are not preserved by the page URL/session, the fresh-browser test
fails; use guided collection until a site-specific replay workflow is built.
Expired sessions, changed layouts, and access restrictions also require attention.
Unattended Dunkin collection is not claimed until the real-PC test succeeds.

Daily scheduling uses Windows Task Scheduler with the current user's interactive
token, least privilege, and no stored Windows password. Jobs run while your PC
is awake and you are signed in; the desktop app can be closed between runs.
Times use the Windows clock, while Excel timestamps use America/New_York.
Keep the application folder in place; disable scheduling before moving it.
Run logs are saved to `logs/`. Store sessions are saved privately in `local_state/`
and excluded from the downloadable bundle. Do not share your local session files.

The taught-page replay and failure checks are tested in actual Chromium with
synthetic menus. The desktop window, Windows task registration, and Dunkin's
live website still require validation on your PC.

## Windows PC: start here

1. Extract the full `DunkinPriceAgent-PC.zip` into a folder on your PC.
2. Install Python **3.12 or newer**, enabling **Add Python to PATH**.
3. Double-click **setup_windows.bat** to install dependencies and Chromium.
4. Double-click **run_windows.bat** to open the collector.
5. Select the correct store and pickup menu on Dunkin's website. Confirm the
   selected address and channel in the panel.
6. Click **Pick name** and then the item's name on the page; repeat for its price.
   Pick or enter its category and exact size/variant.
7. Click **Preview this item** or **Preview similar cards**. Review/correct the rows,
   select them, check the review box, then **Save selected rows**.
8. Visit more categories and size options, repeating capture. Click **Finish store / next**
   when done with each store. Excel is saved in the **reports** folder.

See `START_HERE.txt` for the complete walkthrough. If browser installation fails,
the app also tries an already-installed Microsoft Edge or Chrome. To force Edge:

```bat
run_windows.bat --browser edge
```

Use consistent category and size labels across stores so identical products match.
The app does not automatically visit categories, open size dialogs, or select
stores. It only exports reviewed rows you explicitly save. Selecting the wrong
store, channel, category, or size produces an incorrect comparison: the store
confirmation is yours, not an independent verification by the software.

The page panel can be hidden while navigating. It reappears on the next page with
the saved item count; confirm the store again before saving on a new URL. A new
browser context is opened for each store. Login state/cookies are not saved in
the package or capture journal. Content inside embedded frames or closed shadow
roots may not be pickable; open the provider's menu as its own page when possible.
This tool does not bypass website access restrictions.

Rows are validated as a batch before saving. Identical repeated rows are
deduplicated; conflicting prices for the same item and size are rejected. Reviewed
batches are journaled to `reports/captures/*.jsonl` before acknowledgement. Closing
the browser early retains saved rows in an Excel report with `partial` status;
unsaved previews are lost. Closing the terminal interrupts the run; already-saved
batches remain in the journal, but no finished Excel report is guaranteed.

## Install and try the reporting demo

Use Python 3.12 or later:

```sh
cd /workspace/HelloWorld
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m dunkin_compare --demo
.venv/bin/python -m unittest discover -s tests -v
```

On macOS/Linux with a graphical desktop, install the Playwright browser and run:

```sh
.venv/bin/python -m playwright install chromium
.venv/bin/python -m dunkin_compare --interactive
```

The demo workbook is written to `reports/DEMO_menu_prices_*.xlsx`. All demo prices
are invented fixtures, labeled **SYNTHETIC DEMO**, and are not Dunkin prices.
Use the existing checkout; cloud tasks are isolated and do not need a Git worktree.

## Add stores

Edit these two files with a spreadsheet editor or a text editor:

- `data/parent_stores.csv` — includes 13801 Heathcote Boulevard, Gainesville, VA.
- `data/competitor_stores.csv` — includes 44795 Dulles Overlook Dr, Ashburn, VA.

Columns:

| Column | Meaning |
| --- | --- |
| `store_id` | Your unique label, distinct across both files. |
| `brand` | `Dunkin` for these stores. |
| `address` | Full address, quoted if it contains commas. In interactive mode, confirm that this is the store selected on the website. The automatic structured parser requires an exact address match. |
| `market` | Stores with the same market are compared, e.g. `northern_va`. |
| `channel` | `pickup`, `delivery`, or `in_store`. Currently defaults to **pickup as an assumption**, not a verified site setting. Set this to the actual source channel. |
| `menu_url` | Optional in interactive mode; blank opens Dunkin's homepage so you can select the store. Required for automatic extraction. |
| `profile` | Parser profile from `config/profiles.json`; ignored in interactive mode. |

## Automatic collection (optional; Dunkin integration pending)

Allow `dunkindonuts.com` and its subdomains in cloud environment settings; draft
network additions have been saved, along with `cdn.playwright.dev` for the browser
download. The latest Dunkin response is HTTP 403 (`error code: 1010`), and browser
installation was denied by network policy. Save settings and retry live inspection. The
ordering provider may require additional destinations once identified. Do not
assume that saving a draft changes the running network policy.

After the store URL and profile are verified:

```sh
.venv/bin/python -m dunkin_compare
```

Exit code `0` means all listed stores were collected; `1` means at least one
store failed, was skipped, or ended partially, with details in `Store Status`;
`2` indicates invalid inputs. Interactive stores marked `reviewed` contain
user-confirmed captures, not an assertion of full-menu coverage.
Reports are timestamped and existing files are not overwritten.

The `structured_menu` profile accepts an embedded Schema.org Restaurant with an
exact matching address and a nested `hasMenu` containing MenuSections, MenuItems,
and explicitly priced offers with currencies. This is a general supported data
format, **not a claim that Dunkin publishes this format**. Missing or ambiguous
prices, missing categories, incorrect addresses, and conflicting prices fail
collection. Unknown sizes are listed but withheld from automatic comparison.

A dynamic ordering site needs a verified `browser` profile with these fields:
`location_selector`, `item_selector`, `name_selector`, `category_selector`,
`price_selector`, `variant_selector`, and `currency`. Item fields are CSS selectors
relative to each item card. `location_selector` must identify exactly the selected
store address. An optional `ready_selector` signals that the menu is loaded.
Install Chromium for this mode with:

```sh
PLAYWRIGHT_BROWSERS_PATH=/workspace/HelloWorld/.browser-cache .venv/bin/python -m playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=/workspace/HelloWorld/.browser-cache .venv/bin/python -m dunkin_compare
```

The browser collector currently reads already-rendered item cards. Store-selection
flows, pagination, lazy loading, category tabs, and option dialogs require site-specific
implementation after inspection. It does not automate login or bypass access challenges.
Public HTTPS fetches check `robots.txt`, use timeouts, and process stores sequentially.

## Workbook

- **Menu Prices:** store, address, category, item, size/variant, numeric price,
  currency, collection run completion date/time, source URL(s), and capture method.
- **Comparison:** every parent/competitor pair in the same market with matching
  brand, category, item, explicit size/variant, currency, and channel.
  Difference is **competitor minus parent**; percentage uses the parent price.
- **Unmatched Items:** products without a comparable counterpart, or unknown size.
- **Store Status:** successful and failed collections; a failed store has no price rows.
- **Read Me:** method and limitations, including demo labeling.

No fuzzy name matching is used. Taxes, fees, modifiers, promotions, or in-store
prices are not inferred from an online pickup menu. Collection date/time is
America/New_York with UTC offset, not the date the store last changed its prices.
Interactive journals record individual batch times; the workbook uses run completion
time. Archive each dated workbook for history. Full-menu coverage must be checked
against the real ordering interface before relying on the data for decisions.

## Build the PC ZIP

```sh
python scripts/build_pc_bundle.py
```

Includes source, Windows launchers, instructions, CSV inputs, and synthetic test
fixtures. Excludes virtual environments, installed browsers, Git metadata, reports,
and capture journals. The ZIP does not bundle Python or a browser executable.
