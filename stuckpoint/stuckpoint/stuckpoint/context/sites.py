"""Help policy tables (Person 1). Edit these, not the classifier logic."""

# site (URL host, "www." already stripped by Activity Frames) -> platform name
PRACTICE = {
    "leetcode.com": "leetcode",
    "leetcode.cn": "leetcode",
    "hackerrank.com": "hackerrank",
    "codeforces.com": "codeforces",
    "codechef.com": "codechef",
    "practice.geeksforgeeks.org": "gfg",
    "atcoder.jp": "atcoder",
    "neetcode.io": "neetcode",
}

# Exam / proctored / assessment platforms -> assistant switches itself off.
# Add your college's exam portal here.
EXAM = {
    "mettl.com": "mettl",
    "examly.io": "examly",
    "proctorio.com": "proctorio",
    "hackerearth.com": "hackerearth",
}

# Native apps that mean "working on my own project"
PROJECT_APPS = {
    "Code": "vscode",
    "Visual Studio Code": "vscode",
    "Cursor": "cursor",
    "PyCharm": "pycharm",
    "IntelliJ IDEA": "intellij",
    "Sublime Text": "sublime",
    "Xcode": "xcode",
    "Zed": "zed",
    # Windows / Linux names (capture/backends/common.py APP_NAMES)
    "Windsurf": "windsurf",
    "WebStorm": "webstorm",
    "CLion": "clion",
    "Android Studio": "android-studio",
    "Visual Studio": "visual-studio",
    "Notepad++": "notepad++",
}

# Terminals: project work, but their titles don't name the project
TERMINAL_APPS = {"Terminal", "iTerm2", "Warp", "Alacritty", "kitty", "WezTerm",
                 "Windows Terminal", "Windows PowerShell", "PowerShell", "Command Prompt", "Konsole"}

# Browser page kinds (Activity Frames entity types) that mean project work
PROJECT_PAGE_KINDS = {"local_dev", "repo", "code", "pull_request", "issue"}

# "Looking for help" — attributed to whatever problem the user interrupted
HELP_PAGE_KINDS = {"question", "ai_chat", "search"}
HELP_SITES = {
    "stackoverflow.com", "chatgpt.com", "chat.openai.com", "claude.ai",
    "gemini.google.com", "perplexity.ai", "geeksforgeeks.org",
    "developer.mozilla.org", "docs.python.org", "w3schools.com",
    "google.com", "youtube.com",
}

# Suffixes that browsers / platforms append to window titles
TITLE_NOISE = (
    " - Google Chrome", " — Google Chrome", " - Mozilla Firefox", " — Mozilla Firefox",
    " - Brave", " - Microsoft Edge", " - Safari", " - Arc", " — Firefox", " - Chromium",
    " - Personal", " - Work",                      # Edge profile names
    " - LeetCode", " | LeetCode", " - 力扣（LeetCode）",
    " | HackerRank", " - HackerRank",
    " - Codeforces", " - CodeChef", " | Practice | GeeksforGeeks",
    " - AtCoder", " - NeetCode",
)
