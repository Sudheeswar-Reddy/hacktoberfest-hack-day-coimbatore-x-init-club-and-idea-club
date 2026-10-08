# StuckPoint

> A Chrome extension (with IDE extensions) for students and working developers. It notices when you're stuck while coding and gives help that depends on *where* you are. On **any website or IDE**, it highlights slow code with a GitHub-style hover card showing a faster approach. It also builds an evidence-backed skills report, all inside the extension and powered by Gemma 4.

## Team

**Team Name:** [Team Name]


| Member | Contribution   |
| ------ | -------------- |
| [Name] (Team Lead) | Local engine: FastAPI server, event ingestion into Activity Frames, stuck detection, store, metrics |
| [Name] | Gemma 4 layer: hints, no-code guard, code suggestions with quote verification, evidence gate, report |
| [Name] | Chrome extension: activity tracking, notifications, highlights and hover cards on any site |
| [Name] | Side panel dashboard, VS Code extension, README, demo and submission |


## Problem Statement

### The Problem

When students and developers get stuck on code, they usually fall into one of two bad outcomes:

1. **They struggle alone for too long.** They loop between the editor, errors, Stack Overflow and docs for 30–60 minutes without progress.
2. **They outsource the thinking.** They paste the problem into an AI chatbot, copy the solution and learn nothing. On practice platforms like LeetCode that defeats the purpose of practising; on assignments it's an academic-integrity problem.

Existing AI assistants make this worse. They live inside one editor, so they can't see that you've bounced between LeetCode, Google and ChatGPT for 25 minutes. They apply the same policy everywhere, solving a practice problem as readily as writing boilerplate. And when code *works but is slow*, nobody shows you where, in the place you're actually reading or writing it.

The last problem isn't limited to students. Working developers read and write code in many places every day: their IDE, online editors, GitHub files, Stack Overflow answers, documentation and AI chat answers. Performance feedback today is locked inside one editor or a separate chat window.

### Why We Chose This Problem

Every member of our team has lived both failure modes: the hour-long rabbit hole and the copy-pasted solution that taught us nothing. Coding practice is one of the most common activities for engineering students, so better help at the moment of being stuck, and honest feedback on *how* we code, directly affects learning and placement preparation.

A browser extension is the right place for it: it is where people practise (LeetCode, HackerRank), search (Stack Overflow, Google), read code (GitHub, docs) and ask AI (ChatGPT). It works on every operating system without installing a separate app. IDE extensions cover the projects they build.

## Solution

StuckPoint is a **Chrome extension** (primary) plus **IDE extensions**, backed by a small local engine:

1. **Tracks coding activity across tools.** Which coding site or file you're on and how much you type: counts only, never the keys.
2. **Detects stuck moments**: long time on one problem, loops to help sites, low typing.
3. **Asks before helping:** a Chrome notification, "Stuck on *Coin Change*? Want a hint?", opens the side panel.
4. **Adapts help to context:**

   | Context | Examples | Help | Code suggestions |
   |---|---|---|---|
   | Practice | LeetCode, HackerRank, Codeforces | Hints only, 3 levels, never code | Highlight + explanation; faster code unlocks only after you mark the problem solved |
   | Project | VS Code and other IDEs, online editors (CodeSandbox, StackBlitz, Replit, Colab), localhost | Hint first; full fix on request | Highlight + hover card with faster code + Apply |
   | Review | Read-only code on GitHub, Stack Overflow, docs, blogs, AI chat answers | — | Highlight + hover card with faster code + Copy |
   | Exam | Proctored / assessment sites | Off | Off |

   A **profile setting** fits it to the user:
   - **Professional:** direct answers in your own code.
   - **Student (learner mode):** faster code is held back until you ask, even in projects, so you try first.

5. **Universal inline code suggestions.** Slow or clumsy lines are highlighted wherever code appears. Hovering shows the same card everywhere, like GitHub's hover cards: what's slow, why, complexity before → after, and the better approach.
   - **Live editors on any website:** Monaco, CodeMirror and Ace, the editors behind LeetCode, CodeSandbox, HackerRank-style judges and most online IDEs.
   - **Read-only code blocks on any page:** GitHub, Stack Overflow, documentation, blogs, AI chat answers.
   - **IDEs:** VS Code and its forks (Cursor, Windsurf, VSCodium), in any language.
6. **Skills report in the side panel.** Strengths, weak topics, time-to-unstuck and hints used, with every number verified against measured activity.

### Key Features

- **Chrome extension first:** works on Windows, macOS and Linux; the dashboard lives in Chrome's side panel, with no separate app to open.
- **Hover suggestions on any site:** live editors (Monaco, CodeMirror, Ace) and read-only code blocks. One click on ⚡, or right-click → *Review this code*.
- **IDE extension:** one VS Code extension that also runs in Cursor, Windsurf and VSCodium. Suggestions appear as diagnostics, hover cards and a one-click "⚡ Apply faster version" quick fix, in any language.
- **For students and professionals:** a learner mode that teaches before it tells, and a professional mode that just gives you the faster code.
- **Cross-site stuck detection:** sees the loop between the problem, Stack Overflow, Google and ChatGPT, which an editor plugin alone cannot.
- **Context-aware help policy:** hints only on practice sites, full help on your own projects, off during exams.
- **Graduated hints:** nudge → concept → plain-English plan, so the learner does the solving.
- **Highlight + hover suggestions:** faster approaches shown where the code is, GitHub-style.
- **Verified AI output:** report numbers are recomputed from measured activity, and code suggestions must quote your real code or they are dropped.
- **Privacy by design:**
  - Keystroke *contents* are never recorded, only counts.
  - Code from ordinary web pages is sent only when you click ⚡. Auto-review runs only in editors on coding sites, and can be turned off per site.
  - The API key stays in the local engine, not in the extension.

## Innovation and Differentiation

| Conventional AI coding assistants | StuckPoint |
|---|---|
| Live inside one editor or one website | Any website in Chrome + VS Code-family IDEs, sharing one engine and one view of your activity |
| Respond only when asked | Notice being stuck and *offer* help |
| Same policy everywhere; will solve practice problems | Policy depends on context and profile: hints only where learning or integrity matters |
| Code review only on request, in a chat window | Highlights slow code in place, wherever it is, with a GitHub-style hover card |
| Built either for learners or for professionals | One tool for both: learner mode teaches, professional mode gives the fix |
| Show the optimal solution immediately | On practice sites, the faster code unlocks only after you solve it yourself |
| LLM output is trusted as-is | **"Gemma proposes; code verifies."** Report numbers are recomputed from activity; suggestion line numbers are computed from exact quotes of your code, never taken from the model |

Our core technical idea is **verified inference**. [Activity Frames](https://github.com/nossa-y/activity-frames) separates *measured* facts from *inferred* interpretations, which must carry a confidence level and evidence. Our extensions record activity in Activity Frames' capture format; Activity Frames compiles it into measured episodes; Gemma 4 adds the inferred layer; and our deterministic checks verify Gemma's claims before anything reaches the user.

## Technical Implementation

### Architecture

```mermaid
flowchart LR
    subgraph Chrome["Chrome extension (primary) — every site"]
        T[tracker.js<br/>focus + key/click counts] --> SW[background.js<br/>service worker]
        EB[editor_bridge.js<br/>adapters: Monaco ·<br/>CodeMirror · Ace] <--> EU[code_ui.js<br/>editors + code blocks,<br/>highlights, ⚡ button]
        EU --> HC[hovercard.js<br/>shared GitHub-style card]
        EU <--> SW
        SP[Side panel<br/>Now · Suggestions ·<br/>Report · Settings] <--> SW
        SW --> N[Chrome notifications]
    end
    subgraph IDE["IDEs"]
        VE[VS Code extension<br/>also Cursor · Windsurf · VSCodium]
    end
    SW -- HTTP --> API
    VE -- HTTP --> API
    subgraph Engine["StuckPoint engine · localhost:8765 (Python)"]
        API[FastAPI server] --> ING[Ingestion → capture DB<br/>Activity Frames schema]
        ING --> AF[Activity Frames compiler<br/>measured episodes]
        AF --> DET[Context classifier +<br/>stuck detector]
        DET --> ST[(Local store)]
        API --> LLM[Hints · suggestions ·<br/>topics · report claims]
        API --> REP[Metrics + evidence gate]
    end
    LLM --> G[Gemma 4<br/>Gemini API]
```

### Technology Stack


| Category        | Technologies                |
| --------------- | --------------------------- |
| Frontend        | Chrome extension (Manifest V3, plain JavaScript, Side Panel API, context menus; editor adapters for Monaco, CodeMirror and Ace; shadow-DOM hover cards); VS Code extension (JavaScript, Diagnostics / Hover / Code Action APIs; also runs in Cursor, Windsurf, VSCodium) |
| Backend         | Python 3.10+, FastAPI, Uvicorn (local engine on `127.0.0.1:8765`) |
| Database        | SQLite: capture database in Activity Frames' schema; local store for signals, hints, solved flags and report claims |
| AI / ML         | Gemma 4 (`gemma-4-31b-it`) via the Gemini API |
| Infrastructure  | Runs on the user's machine; model inference via Google's Gemini API |
| APIs / Services | Gemini API (`google-genai` SDK); Activity Frames Python API |


### How It Works

**1. Activity tracking (extensions).** The Chrome extension's content script sends a heartbeat every 10 seconds while a page is focused: page title and URL. It also sends counts of keystrokes and clicks. The VS Code extension sends the same for the active file. Key values are never captured.

**2. Ingestion into Activity Frames (engine).** The engine writes these events into a SQLite database using the tables Activity Frames reads (`frames` and `ui_events`). Keystroke counts are stored as placeholder characters, so counts are exact while no typed text is ever stored. Activity Frames then compiles the raw events into *frames*: bounded, measured episodes such as "leetcode.com, *Coin Change*, 20:12–20:20, 8.2 active minutes, 58 keystrokes", each with evidence pointers. Activity Frames' own recorder is macOS-only; our extensions make the same pipeline work on every OS.

**3. Context classification.** Each frame is labelled practice, project, exam or other from its site and window title. LeetCode problem names come from the page title, e.g. `322. Coin Change - LeetCode` → `leetcode:coin-change`.

**4. Stuck detection.** A background loop checks the last 30 minutes against three deterministic rules:
- **Time:** long time on one problem.
- **Loops:** repeated problem → help site → problem cycles.
- **Low input:** a low typing rate.

When rules agree, the signal is confirmed; borderline cases go to Gemma 4. The extension polls the engine and shows a Chrome notification.

**5. Hints.** In the side panel, each request reveals one more level (nudge → concept → plan). On practice sites the prompt forbids code, and a guard blocks anything code-like and regenerates. Code is never shown, even if the user asks.

**6. Universal code suggestions.** The extension finds code wherever it appears:
- **Live editors on any site:** an adapter for each editor family reads the code and adds highlights (Monaco decorations, CodeMirror `markText`, Ace markers).
- **Read-only code blocks:** `pre`/`code` blocks on any page, highlighted with an overlay that never changes the page's own text.
- **VS Code and its forks.**

When typing pauses in a coding-site editor, or when the user clicks ⚡, the engine asks Gemma 4 for up to three improvements. Each must include an **exact quote** of the user's code. The engine finds that quote, **computes the line numbers itself**, and drops any suggestion whose quote doesn't exist.

The engine also decides the mode (practice, project, review or exam) from the site and surface. Replacement code is withheld on practice sites until the problem is marked solved, and in learner mode until the user asks.

The same hover card appears everywhere, rendered in a shadow DOM so no website's styles can break it. It offers **Apply** in editable editors and **Copy** on read-only code. In VS Code, suggestions are Information diagnostics with a hover card and an "Apply faster version" quick fix.

**7. Skills report.** Activity is grouped into per-problem sessions; Gemma 4 tags topics and drafts claims (strengths, weaknesses, recommendations). The **evidence gate** recomputes every number from the measured metrics and checks every cited problem exists. Claims are marked verified, low-confidence or rejected, with the reason shown in the side panel.

### Technical Decisions

- **Extensions as the recorder.** Writing events in Activity Frames' capture schema keeps its deterministic, evidence-linked compiler and makes it cross-platform.
- **Local engine between extensions and Gemma.** One shared brain for Chrome and VS Code, reusing the same Python detection and Gemma code, and keeping the API key out of client-side extension code.
- **Deterministic first, LLM second.** Stuck detection, line ranges and report numbers are computed by code. Gemma 4 is used only where judgement or language is needed.
- **Never trust model line numbers.** Suggestions are anchored by exact quotes; unmatched quotes are discarded.
- **Editor adapters, one card.** Most web editors are built on Monaco, CodeMirror or Ace, so three small adapters cover most sites. Static code blocks cover the rest. A single shared hover card keeps the experience identical everywhere.
- **Click-to-review outside coding sites.** Reading a blog or a GitHub file never sends code anywhere unless you click ⚡. This keeps it private and keeps model calls cheap.
- **One VS Code extension, many IDEs.** Cursor, Windsurf and VSCodium implement the VS Code extension API, so the same extension runs in all of them.
- **Earned answers for learners.** On practice sites, and in learner mode, faster code is withheld until the user has solved the problem or asks, so suggestions teach rather than replace practice. Professionals get the fix directly.
- **Counts, not content.** Typing is measured as counts only; the engine stores no typed text.

## Implementation During the Hackathon

> _To be updated during the Hack Day. Tick only what actually works._

- [x] Context classifier (practice / project / exam) and stuck detector with tests
- [x] Gemma 4 client with JSON validation, retries, caching and logging
- [x] Graduated hints with the no-code guard; borderline stuck judgement; topic tagging; report-claim drafting
- [ ] Local engine: FastAPI server, ingestion into Activity Frames, background detection loop
- [ ] Chrome extension: tracking, notifications, side panel with Settings (profile, per-site off)
- [ ] Hover cards on Monaco editors (any site) and read-only code blocks (any site)
- [ ] CodeMirror and Ace editor adapters
- [ ] Code suggestions with quote verification and the mode/profile policy
- [ ] Evidence gate + skills report in the side panel
- [ ] VS Code extension: diagnostics, hover cards, quick fix (also tested in Cursor)
- [ ] Language server for other IDEs (Neovim, JetBrains, Sublime, Zed, Helix)

### Team Contributions

- **[Member Name]:** Local engine, ingestion into Activity Frames, stuck detection, store, metrics
- **[Member Name]:** Gemma 4 integration, hints and guard, code suggestions, evidence gate, report
- **[Member Name]:** Chrome extension core: tracking, notifications, editor adapters, highlights and hover cards on any site
- **[Member Name]:** Side panel dashboard, VS Code extension, README, demo video, submission

## Working Application

**Live Application:** [Live URL]

StuckPoint is a browser extension plus a local engine, so it runs on the user's machine rather than as a hosted website. Judges can install it in a few minutes by following [Setup and Usage](#setup-and-usage): start the engine, then load the unpacked extension in Chrome. [Add a link to a release zip of the extension here if one is published.]

## Demo Video

**Demo Video:** [Video URL]

The demo covers:

1. On LeetCode, a user gets stuck on *Coin Change*, bouncing to Stack Overflow and ChatGPT; a Chrome notification offers help.
2. The side panel gives graduated hints and refuses to show code, even when asked.
3. On *Two Sum*, a working nested-loop solution gets highlighted; the hover card explains the O(n²) → O(n) improvement. After marking it solved, the card shows the faster code.
4. In professional mode, a code block on Stack Overflow (or GitHub) is reviewed with one click on ⚡; the same hover card appears, with Copy.
5. In VS Code, a slow pattern in a project file is highlighted; hover shows the suggestion, and the quick fix applies it. The same extension runs in Cursor.
6. The side-panel report shows verified, low-confidence and rejected claims, with reasons.

## Open Source and AI Usage

### AI / Models

- **Gemma 4 (`gemma-4-31b-it`, via the Gemini API):**
  - Judges borderline stuck patterns.
  - Writes graduated, code-free hints on practice sites, and full fixes on personal projects.
  - Finds slower-than-necessary code and proposes faster approaches (anchored by exact quotes and verified by the engine).
  - Tags problems with skill topics.
  - Drafts the skills report as structured JSON, which the evidence gate verifies.

  [Update if the `gemma-4-26b-a4b-it` fallback was used.]

### Open Source Components

- **[Activity Frames](https://github.com/nossa-y/activity-frames) (MIT):** Compiles the extensions' raw activity events into deterministic, evidence-linked episodes. Its schema and two-tier measured/inferred specification are the foundation of our data model.
- **[FastAPI](https://github.com/fastapi/fastapi) (MIT) + [Uvicorn](https://github.com/encode/uvicorn) (BSD):** Local engine HTTP server.
- **[google-genai](https://github.com/googleapis/python-genai) (Apache 2.0):** Python SDK for calling Gemma 4 through the Gemini API.
- **[jsonschema](https://github.com/python-jsonschema/jsonschema) (MIT):** Validates every Gemma 4 response.
- **Monaco, CodeMirror and Ace editor APIs** (as embedded by the websites that use them; all open source): used at runtime to read code and add highlights. Not bundled.
- **Dataset:** N/A. All data comes from the user's own activity; demo data was recorded by team members during the Hack Day.
- **API / Service:** Gemini API (Google AI Studio), hosted inference for Gemma 4.

## Setup and Usage

> _Verify these steps on a clean machine before submitting._

### Prerequisites

- Google Chrome (or another Chromium browser with Side Panel support)
- Python 3.10 or newer
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
- Optional: VS Code 1.80+ for the IDE extension

### Installation

```bash
git clone [repository-url]
cd stuckpoint
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then add your GEMINI_API_KEY
```

**Chrome extension:** open `chrome://extensions`, enable **Developer mode**, click **Load unpacked**, and select `extensions/chrome`.

**VS Code extension (also Cursor, Windsurf, VSCodium):** open the `extensions/vscode` folder in the editor and press **F5** to launch it in an Extension Development Host window. Set your profile in Settings → `stuckpoint.profile` (`professional` or `student`).

**Other IDEs (Neovim, JetBrains, Sublime Text, Zed, Helix):** [if built] point your editor's LSP client at `python -m stuckpoint lsp`. [If not built, this is listed under Future work.]

### Environment Variables

```env
GEMINI_API_KEY=your-key-here
GEMMA_MODEL=gemma-4-31b-it
STUCKPOINT_SOURCE=live
AFRAMES_DB=data/capture.sqlite
ENGINE_PORT=8765
# Minutes on one problem before StuckPoint offers help (3 for a quick demo)
STUCK_THRESHOLD_MIN=15
```

### Running the Project

```bash
# Start the local engine (keep it running)
python -m stuckpoint serve
```

Then use Chrome (and VS Code) normally. Useful extra commands:

```bash
python -m stuckpoint check-llm   # verify the Gemma 4 connection
python -m stuckpoint demo        # run detection on sample data (no extension needed)
python -m pytest                 # run the tests
```

### Usage

1. Start the engine, then click the StuckPoint icon in Chrome to open the side panel. In **Settings**, choose **Professional** or **Student (learner mode)**.
2. Code as usual: on LeetCode, in an online editor, or in your IDE. The **Now** tab shows the detected context (Practice / Project / Review / Exam).
3. When you're stuck, a notification offers help. Open it for graduated hints: **Next hint** reveals more; **Solved ✓** marks the problem done.
4. **Hover suggestions, anywhere:**
   - **Editors on coding sites:** slow code is highlighted automatically when you pause typing.
   - **Any other code on a web page:** hover the code block and click ⚡, or select code and right-click → **StuckPoint: Review this code**.
   - Hover a highlight to see the card. Use **Apply** (editors) or **Copy** (read-only code). On practice sites and in learner mode, the faster code appears after you solve the problem or click **Show me**.
   - **In your IDE:** use **⚡ Apply faster version** from the quick-fix menu.
5. Turn StuckPoint off for any site from **Settings**. It is always off on exam sites.
6. Open the **Report** tab and click **Refresh** for your skills report. Click **Show evidence** on any claim to see what it's based on.

## Devpost Submission

**Devpost Project:** [Devpost Project URL]

[Add the link to the team's Devpost submission. Ensure the Devpost project page is complete and contains the required project information, links, media, and team details.]

## Challenges and Learnings

> _To be completed after the Hack Day._

- **Challenges:** [e.g. Activity Frames' recorder being macOS-only (solved by making the extensions the recorder), reaching each website's code editor from an extension, keeping the hover card's styling safe on any site, MV3 service-worker lifecycles, keeping hints from leaking code, anchoring model suggestions to real lines]

### Future work

- Language server (`python -m stuckpoint lsp`) so every LSP editor, including Neovim, JetBrains (via LSP4IJ), Sublime Text, Zed and Helix, gets the same highlights and hover cards. [Move to Key Features if built during the event.]
- Firefox and Edge builds of the browser extension.
- Team mode for professionals: shared, opt-in suggestion patterns across a codebase.
- **Learnings:** [What the team learned technically and about the problem]

## Credits and License

### Credits

- [Activity Frames](https://github.com/nossa-y/activity-frames) by Nossa Iyamu: episodic activity compilation (MIT)
- [Gemma 4](https://ai.google.dev/gemma) by Google: open-weight language model, used via the [Gemini API](https://ai.google.dev)
- [FastAPI](https://fastapi.tiangolo.com), [Uvicorn](https://www.uvicorn.org), [google-genai](https://github.com/googleapis/python-genai), [jsonschema](https://python-jsonschema.readthedocs.io)
- [Monaco Editor](https://github.com/microsoft/monaco-editor) (MIT), accessed at runtime on LeetCode
- Built at Hacktoberfest Hack Day Coimbatore 2026, hosted by INIT Club & iDEA Club, Amrita Vishwa Vidyapeetham, powered by MLH

### License

This project is licensed under the [MIT License](LICENSE).

## Submission Checklist

- [ ] Project title and description added
- [ ] All team members listed
- [ ] Problem clearly explained
- [ ] Reason for choosing the problem explained
- [ ] Solution and key features documented
- [ ] Innovation and differentiation explained
- [ ] Architecture included
- [ ] Technical implementation documented
- [ ] Work completed during the hackathon documented
- [ ] Team contributions documented
- [ ] Working application is functional
- [ ] Live application link added where applicable
- [ ] Demo video added
- [ ] AI and open-source components documented
- [ ] Setup and usage instructions tested
- [ ] Challenges and learnings documented
- [ ] Devpost submission completed
- [ ] Devpost link added
- [ ] Credits added
- [ ] License added
- [ ] Repository is organized and complete
