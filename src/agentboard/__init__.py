"""The board between agent sessions (post, claim, handoff, pickup, done, reply, wait, status, sessions, whoami, link, setup).

- config.py: where the board lives and what it calls itself (a wrapper calls configure())
- identity.py: the actor, the session id and name, the repo you're in
- tools.py: the agent tools recognised by name, the only place that names them
- store.py: where the lines are kept: the plain file (FileStore), or another Store given to configure()
- board.py: post, read, the views status uses, the [board] nudge
- waits.py: open items (what a piece of work waits on) and their checks; a wrapper gives it its commands
- cli.py: the typer app and the `agents` console script (a wrapper can mount the app as a subcommand)
"""

__version__ = "0.3.0"
