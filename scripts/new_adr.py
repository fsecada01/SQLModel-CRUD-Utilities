"""Create the next numbered ADR from the template: ``just adr "Title"``."""

import re
import sys
from datetime import date
from pathlib import Path

ADR_DIR = Path(__file__).resolve().parent.parent / "docs" / "adr"
TEMPLATE = """# {num}. {title}

- Status: proposed
- Date: {today}

## Context
What forces are at play? What problem prompted this?

## Decision
What we are doing, in one or two paragraphs.

## Consequences
What becomes easier or harder. Follow-ups, risks, how to revisit.

## Alternatives considered
Options rejected and why. Omit the section if there are none.
"""


def main(title: str) -> Path:
    numbers = [
        int(m.group(1))
        for p in ADR_DIR.glob("[0-9]*.md")
        if (m := re.match(r"(\d+)-", p.name))
    ]
    num = f"{max(numbers, default=0) + 1:04d}"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
    path = ADR_DIR / f"{num}-{slug}.md"
    path.write_text(
        TEMPLATE.format(num=num, title=title, today=date.today()),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit('usage: new_adr.py "Decision title"')
    print(main(sys.argv[1]))
